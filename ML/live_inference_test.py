import os
import pickle
import numpy as np
import pandas as pd
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import urllib.parse
from feature_extraction import extract_event_features

# Load trained Random Forest model and preprocessors
with open("data/models/RandomForest.pkl", "rb") as f:
    rf_model = pickle.load(f)

with open("data/models/preprocessors.pkl", "rb") as f:
    preproc = pickle.load(f)

imputer = preproc["imputer"]
scaler = preproc["scaler"]
feature_cols = preproc["features"]

class NarcoscanAPIHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/predict":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            
            try:
                data = json.loads(body)
                # Convert raw timeseries samples to DataFrame
                df_raw = pd.DataFrame(data["timeseries"])
                
                # Extract 108 features in real time
                feat_dict = extract_event_features(df_raw)
                
                # Prepare feature vector matching training columns
                X_raw = pd.DataFrame([feat_dict])
                X_feat = X_raw[[c for c in feature_cols if c in X_raw.columns]]
                for c in feature_cols:
                    if c not in X_feat.columns:
                        X_feat[c] = 0.0
                X_feat = X_feat[feature_cols]
                
                # Preprocess & scale
                X_imp = imputer.transform(X_feat)
                X_sc = scaler.transform(X_imp)
                
                # Real AI inference
                pred_class = int(rf_model.predict(X_sc)[0])
                probs = rf_model.predict_proba(X_sc)[0].tolist()
                
                labels = ["NORMAL", "UNKNOWN", "HIGH_RISK_SCREENING_EVENT"]
                
                response = {
                    "status": "success",
                    "model": "RandomForestClassifier (200 Trees)",
                    "prediction": labels[pred_class],
                    "class_index": pred_class,
                    "probabilities": {
                        "NORMAL": round(probs[0], 4),
                        "UNKNOWN": round(probs[1], 4),
                        "HIGH_RISK": round(probs[2], 4)
                    },
                    "features_extracted_count": len(feature_cols),
                    "key_metrics": {
                        "multimodal_score": round(float(feat_dict.get("multimodal_anomaly_score", 0)), 3),
                        "gas_correlation": round(float(feat_dict.get("gas_correlation", 0)), 3),
                        "max_gas_response": round(float(feat_dict.get("max_gas_response", 0)), 1),
                        "deltaT_max": round(float(feat_dict.get("deltaT_max", 0)), 2)
                    }
                }
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))
                return
                
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
                return
                
        super().do_POST()

def test_inference():
    print("Testing live inference with real raw data...")
    df_raw = pd.read_csv("data/raw_timeseries.csv")
    sample_evt = df_raw[df_raw["synthetic_condition"] == "strong_coordinated_voc_anomaly"].head(200)
    
    feat_dict = extract_event_features(sample_evt)
    X_raw = pd.DataFrame([feat_dict])
    X_feat = X_raw[[c for c in feature_cols if c in X_raw.columns]]
    for c in feature_cols:
        if c not in X_feat.columns:
            X_feat[c] = 0.0
    X_feat = X_feat[feature_cols]
    
    X_imp = imputer.transform(X_feat)
    X_sc = scaler.transform(X_imp)
    
    pred = rf_model.predict(X_sc)[0]
    probs = rf_model.predict_proba(X_sc)[0]
    
    labels = ["NORMAL", "UNKNOWN", "HIGH_RISK_SCREENING_EVENT"]
    print(f"-> Sample Event: strong_coordinated_voc_anomaly")
    print(f"-> Real Model Prediction: {labels[pred]}")
    print(f"-> Class Probabilities: NORMAL={probs[0]:.2%}, UNKNOWN={probs[1]:.2%}, HIGH_RISK={probs[2]:.2%}")

if __name__ == "__main__":
    test_inference()
