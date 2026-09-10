import os
import math
import time
import torch
import torch.nn as nn
import torch.nn.functional as F

# NARCOSCAN: Multi-Modal Chemical-Temporal Foundation Model (NARCO-LFM-1.1B)
# ==========================================================================

class RotaryEmbedding(nn.Module):
    def __init__(self, dim, max_seq_len=2048):
        super().__init__()
        inv_freq = 1.0 / (10000 ** (torch.arange(0, dim, 2).float() / dim))
        self.register_buffer("inv_freq", inv_freq)
        self.max_seq_len = max_seq_len

    def forward(self, x, seq_len):
        t = torch.arange(seq_len, device=x.device, dtype=self.inv_freq.dtype)
        freqs = torch.einsum("i,j->ij", t, self.inv_freq)
        emb = torch.cat((freqs, freqs), dim=-1)
        return emb.cos(), emb.sin()

def rotate_half(x):
    x1, x2 = x[..., :x.shape[-1] // 2], x[..., x.shape[-1] // 2:]
    return torch.cat((-x2, x1), dim=-1)

def apply_rotary_pos_emb(q, k, cos, sin):
    cos = cos.unsqueeze(0).unsqueeze(1)
    sin = sin.unsqueeze(0).unsqueeze(1)
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed

class MultimodalPatchTokenizer(nn.Module):
    """Tokenizes raw 10 Hz multi-channel sensor arrays into continuous token representations."""
    def __init__(self, in_channels=8, d_model=2048, patch_size=5):
        super().__init__()
        self.patch_size = patch_size
        self.proj = nn.Sequential(
            nn.Conv1d(in_channels, d_model // 2, kernel_size=patch_size, stride=patch_size),
            nn.GELU(),
            nn.Conv1d(d_model // 2, d_model, kernel_size=3, padding=1)
        )
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x):
        x = self.proj(x)
        x = x.transpose(1, 2)
        return self.norm(x)

class MultiHeadAttentionWithRoPE(nn.Module):
    def __init__(self, d_model=2048, n_heads=32, dropout=0.1):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        assert self.head_dim * n_heads == d_model, "d_model must be divisible by n_heads"

        self.q_proj = nn.Linear(d_model, d_model, bias=False)
        self.k_proj = nn.Linear(d_model, d_model, bias=False)
        self.v_proj = nn.Linear(d_model, d_model, bias=False)
        self.out_proj = nn.Linear(d_model, d_model, bias=False)
        
        self.rotary = RotaryEmbedding(self.head_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        B, S, D = x.shape
        q = self.q_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)

        cos, sin = self.rotary(x, S)
        q, k = apply_rotary_pos_emb(q, k, cos, sin)

        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        attn_weights = F.softmax(scores, dim=-1)
        attn_weights = self.dropout(attn_weights)
        
        out = torch.matmul(attn_weights, v)
        out = out.transpose(1, 2).contiguous().view(B, S, D)
        return self.out_proj(out)

class SwiGLUFeedForward(nn.Module):
    """SwiGLU Feed-Forward Network used in billion-parameter foundation LLMs."""
    def __init__(self, d_model=2048, d_ff=8192, dropout=0.1):
        super().__init__()
        self.w1 = nn.Linear(d_model, d_ff, bias=False)
        self.w2 = nn.Linear(d_ff, d_model, bias=False)
        self.w3 = nn.Linear(d_model, d_ff, bias=False)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        return self.dropout(self.w2(F.silu(self.w1(x)) * self.w3(x)))

class TransformerBlock(nn.Module):
    def __init__(self, d_model=2048, n_heads=32, d_ff=8192, dropout=0.1):
        super().__init__()
        self.norm1 = nn.LayerNorm(d_model)
        self.attn = MultiHeadAttentionWithRoPE(d_model, n_heads, dropout)
        self.norm2 = nn.LayerNorm(d_model)
        self.ffn = SwiGLUFeedForward(d_model, d_ff, dropout)

    def forward(self, x):
        x = x + self.attn(self.norm1(x))
        x = x + self.ffn(self.norm2(x))
        return x

class NarcoMultimodalFoundationModel(nn.Module):
    """
    NARCO-LFM (Large Foundation Model for Chemical-Thermal Threat Screening)
    Configurable from 12M Edge parameters to 1.12 Billion Cloud parameters.
    """
    def __init__(
        self,
        in_channels=8,
        d_model=2048,
        n_layers=32,
        n_heads=32,
        d_ff=8192,
        patch_size=5,
        num_classes=3,
        latent_dim=1024,
        dropout=0.1
    ):
        super().__init__()
        self.d_model = d_model
        self.n_layers = n_layers
        self.tokenizer = MultimodalPatchTokenizer(in_channels, d_model, patch_size)
        
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_model) * 0.02)
        
        self.blocks = nn.ModuleList([
            TransformerBlock(d_model, n_heads, d_ff, dropout)
            for _ in range(n_layers)
        ])
        
        self.final_norm = nn.LayerNorm(d_model)
        
        self.classifier = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, num_classes)
        )
        
        self.latent_projector = nn.Sequential(
            nn.Linear(d_model, latent_dim),
            nn.GELU(),
            nn.Linear(latent_dim, latent_dim)
        )

    def count_parameters(self):
        total = sum(p.numel() for p in self.parameters())
        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        return total, trainable

    def forward(self, x):
        B = x.shape[0]
        tokens = self.tokenizer(x)
        
        cls_tokens = self.cls_token.expand(B, -1, -1)
        tokens = torch.cat((cls_tokens, tokens), dim=1)
        
        for block in self.blocks:
            tokens = block(tokens)
            
        normed = self.final_norm(tokens)
        cls_repr = normed[:, 0]
        
        logits = self.classifier(cls_repr)
        latent_embeddings = self.latent_projector(cls_repr)
        
        return {
            "logits": logits,
            "probabilities": F.softmax(logits, dim=-1),
            "threat_latent": latent_embeddings
        }

def get_model_config(scale="1.1B"):
    configs = {
        "12M": {
            "d_model": 256,
            "n_layers": 8,
            "n_heads": 8,
            "d_ff": 1024,
            "desc": "Edge Quantized Micro-Transformer (ESP32 / Jetson Nano)"
        },
        "150M": {
            "d_model": 768,
            "n_layers": 16,
            "n_heads": 12,
            "d_ff": 3072,
            "desc": "Medium Multi-Channel Transformer (High-Throughput Gateway)"
        },
        "1.1B": {
            "d_model": 2048,
            "n_layers": 32,
            "n_heads": 32,
            "d_ff": 8192,
            "desc": "Billion-Parameter Multimodal Chemical Foundation Model (Cloud Server)"
        }
    }
    return configs.get(scale, configs["1.1B"])

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NARCOSCAN Billion-Parameter Foundation Model")
    parser.add_argument("--scale", type=str, default="1.1B", choices=["12M", "150M", "1.1B"], help="Model parameter scale")
    args = parser.parse_args()

    cfg = get_model_config(args.scale)
    print("=" * 75)
    print(f"  NARCOSCAN MULTIMODAL CHEMICAL-TEMPORAL FOUNDATION MODEL ({args.scale})")
    print(f"  Configuration: {cfg['desc']}")
    print("=" * 75)

    model = NarcoMultimodalFoundationModel(
        in_channels=8,
        d_model=cfg["d_model"],
        n_layers=cfg["n_layers"],
        n_heads=cfg["n_heads"],
        d_ff=cfg["d_ff"]
    )

    total_params, trainable_params = model.count_parameters()
    print(f"\n* Model Architecture Details:")
    print(f"  - Layers (Transformer Blocks): {cfg['n_layers']}")
    print(f"  - Hidden Dimension (d_model):  {cfg['d_model']}")
    print(f"  - Attention Heads:            {cfg['n_heads']} (Head Dim: {cfg['d_model'] // cfg['n_heads']})")
    print(f"  - Feedforward SwiGLU (d_ff):  {cfg['d_ff']}")
    if total_params >= 1e9:
        print(f"  - Total Parameters:           {total_params:,} ({total_params / 1e9:.3f} Billion Parameters)")
    else:
        print(f"  - Total Parameters:           {total_params:,} ({total_params / 1e6:.1f} Million Parameters)")
    print(f"  - Trainable Parameters:       {trainable_params:,}")
    print(f"  - Precision Footprint (FP16): {total_params * 2 / (1024**3):.2f} GB VRAM")
    print(f"  - Precision Footprint (INT8): {total_params * 1 / (1024**3):.2f} GB VRAM")

    print("\n* Executing Multi-Channel Forward Pass Benchmark...")
    dummy_input = torch.randn(1, 8, 200)
    
    t0 = time.time()
    with torch.no_grad():
        out = model(dummy_input)
    latency_ms = (time.time() - t0) * 1000

    print(f"  - Input Shape:                {list(dummy_input.shape)} (20.0s @ 10 Hz Multimodal Stream)")
    print(f"  - Output Logits:              {list(out['logits'].shape)} -> Classes [NORMAL, UNKNOWN, HIGH_RISK]")
    print(f"  - Threat Latent Vector:       {list(out['threat_latent'].shape)} (Forensic Reasoning Vector)")
    print(f"  - Forward Pass Latency:       {latency_ms:.2f} ms")
    print("=" * 75)
