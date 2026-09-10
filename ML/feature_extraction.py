"""
Feature extraction utility for NARCOSCAN synthetic dataset.
DISCLAIMER: This data is SYNTHETIC and DOES NOT represent real narcotics/explosives measurements.
"""
import os
import warnings
import numpy as np
import pandas as pd
from scipy.fft import fft, fftfreq

warnings.filterwarnings('ignore', category=RuntimeWarning)

def extract_fft_features(signal, sampling_rate=10, prefix=''):
    features = {}
    N = len(signal)
    if N < 2:
        features.update({
            f'{prefix}dominant_freq': 0.0,
            f'{prefix}spectral_energy': 0.0,
            f'{prefix}low_freq_energy': 0.0,
            f'{prefix}high_freq_energy': 0.0,
            f'{prefix}spectral_entropy': 0.0
        })
        return features

    yf = fft(signal)
    xf = fftfreq(N, 1 / sampling_rate)
    
    power_spectrum = np.abs(yf)**2
    
    positive_freqs = xf > 0
    xf_pos = xf[positive_freqs]
    power_pos = power_spectrum[positive_freqs]
    
    if len(power_pos) == 0 or np.all(power_pos == 0):
        dom_freq = 0.0
    else:
        dom_freq = xf_pos[np.argmax(power_pos)]
        
    total_energy = np.sum(power_spectrum) / N
    
    low_idx = (xf_pos >= 0) & (xf_pos <= 1)
    high_idx = (xf_pos > 1) & (xf_pos <= 5)
    
    low_energy = np.sum(power_pos[low_idx]) / N if np.any(low_idx) else 0.0
    high_energy = np.sum(power_pos[high_idx]) / N if np.any(high_idx) else 0.0
    
    p = power_pos / np.sum(power_pos) if np.sum(power_pos) > 0 else np.zeros_like(power_pos)
    p_non_zero = p[p > 0]
    entropy = -np.sum(p_non_zero * np.log2(p_non_zero)) if len(p_non_zero) > 0 else 0.0
    
    features.update({
        f'{prefix}dominant_freq': float(dom_freq),
        f'{prefix}spectral_energy': float(total_energy),
        f'{prefix}low_freq_energy': float(low_energy),
        f'{prefix}high_freq_energy': float(high_energy),
        f'{prefix}spectral_entropy': float(entropy)
    })
    
    return features

def extract_gas_features(event_df, sensor_name, sampling_rate=10):
    signal = event_df[sensor_name].values
    n_samples = len(signal)
    
    if n_samples == 0:
        signal = np.zeros(1)
        n_samples = 1

    baseline = np.median(signal[:10]) if n_samples >= 10 else np.median(signal)
    diffs = np.diff(signal)
    
    signal_minus_baseline = signal - baseline
    pos_mask = signal_minus_baseline > 0
    auc = np.trapz(signal_minus_baseline[pos_mask]) if np.any(pos_mask) else 0.0
    
    std_baseline = np.std(signal[:10]) if n_samples >= 10 else np.std(signal)
    response_mask = signal > (baseline + 2 * std_baseline)
    response_duration = np.sum(response_mask) / sampling_rate
    
    peak_idx = np.argmax(signal)
    peak_val = signal[peak_idx]
    
    recovery_time = 0.0
    if peak_idx < n_samples - 1:
        post_peak = signal[peak_idx:]
        recovery_thresh = baseline + 0.1 * (peak_val - baseline)
        recovery_indices = np.where(post_peak <= recovery_thresh)[0]
        if len(recovery_indices) > 0:
            recovery_time = recovery_indices[0] / sampling_rate
        else:
            recovery_time = (n_samples - 1 - peak_idx) / sampling_rate

    first_rise_idx = np.where(response_mask)[0]
    if len(first_rise_idx) > 0 and first_rise_idx[0] < peak_idx:
        time_to_peak = (peak_idx - first_rise_idx[0]) / sampling_rate
    else:
        time_to_peak = peak_idx / sampling_rate

    features = {
        f'{sensor_name}_mean': np.mean(signal),
        f'{sensor_name}_median': np.median(signal),
        f'{sensor_name}_min': np.min(signal),
        f'{sensor_name}_max': np.max(signal),
        f'{sensor_name}_std': np.std(signal),
        f'{sensor_name}_peak_amplitude': peak_val - baseline,
        f'{sensor_name}_baseline': baseline,
        f'{sensor_name}_max_deviation': np.max(np.abs(signal_minus_baseline)),
        f'{sensor_name}_rise_rate': np.max(diffs) if len(diffs) > 0 else 0.0,
        f'{sensor_name}_fall_rate': np.max(-diffs) if len(diffs) > 0 else 0.0,
        f'{sensor_name}_auc': auc,
        f'{sensor_name}_response_duration': response_duration,
        f'{sensor_name}_recovery_time': recovery_time,
        f'{sensor_name}_time_to_peak': time_to_peak
    }
    
    fft_feats = extract_fft_features(signal, sampling_rate, prefix=f'{sensor_name}_')
    features.update(fft_feats)
    
    return {k: np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0) for k, v in features.items()}

def extract_thermal_features(event_df, sampling_rate=10):
    t_temp = event_df['target_temperature_C'].values if 'target_temperature_C' in event_df.columns else np.zeros(1)
    d_temp = event_df['delta_temperature_C'].values if 'delta_temperature_C' in event_df.columns else np.zeros(1)
    
    dt_diff = np.diff(d_temp) * sampling_rate
    
    return {
        'target_temp_mean': np.nan_to_num(np.mean(t_temp)),
        'target_temp_max': np.nan_to_num(np.max(t_temp)),
        'target_temp_min': np.nan_to_num(np.min(t_temp)),
        'deltaT_mean': np.nan_to_num(np.mean(d_temp)),
        'deltaT_max': np.nan_to_num(np.max(d_temp)),
        'deltaT_std': np.nan_to_num(np.std(d_temp)),
        'deltaT_rate_of_change': np.nan_to_num(np.max(np.abs(dt_diff))) if len(dt_diff) > 0 else 0.0
    }

def extract_environmental_features(event_df):
    env_temp = event_df['ambient_temperature_C'].values if 'ambient_temperature_C' in event_df.columns else np.zeros(1)
    hum = event_df['humidity_percent'].values if 'humidity_percent' in event_df.columns else np.zeros(1)
    pres = event_df['atmospheric_pressure_hPa'].values if 'atmospheric_pressure_hPa' in event_df.columns else np.zeros(1)
    
    return {
        'env_temp_mean': np.nan_to_num(np.mean(env_temp)),
        'env_temp_range': np.nan_to_num(np.max(env_temp) - np.min(env_temp)),
        'humidity_mean': np.nan_to_num(np.mean(hum)),
        'humidity_range': np.nan_to_num(np.max(hum) - np.min(hum)),
        'pressure_mean': np.nan_to_num(np.mean(pres)),
        'pressure_range': np.nan_to_num(np.max(pres) - np.min(pres))
    }

def extract_motion_features(event_df):
    m_count = event_df['motion_count'].values if 'motion_count' in event_df.columns else np.zeros(1)
    pir = event_df['pir_motion'].values if 'pir_motion' in event_df.columns else np.zeros(1)
    prox = event_df['proximity_cm'].values if 'proximity_cm' in event_df.columns else np.zeros(1)
    
    return {
        'total_motion_count': np.nan_to_num(np.max(m_count)),
        'pct_window_motion': np.nan_to_num(np.mean(pir == 1)) if len(pir) > 0 else 0.0,
        'proximity_min': np.nan_to_num(np.min(prox)),
        'proximity_mean': np.nan_to_num(np.mean(prox))
    }

def extract_fusion_features(gas_features_dict, event_df):
    mq_cols = ['mq1', 'mq2', 'mq3', 'mq4']
    valid_cols = [c for c in mq_cols if c in event_df.columns]
    
    corr = 0.0
    if len(valid_cols) > 1:
        corr_matrix = event_df[valid_cols].corr().values
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        valid_corrs = corr_matrix[mask]
        valid_corrs = valid_corrs[~np.isnan(valid_corrs)]
        if len(valid_corrs) > 0:
            corr = np.mean(valid_corrs)
            
    peaks = [gas_features_dict.get(f'{sensor}_peak_amplitude', 0.0) for sensor in mq_cols]
    max_resp = np.max(peaks) if peaks else 0.0
    mean_resp = np.mean(peaks) if peaks else 0.0
    var_resp = np.var(peaks) if peaks else 0.0
    
    chem_therm_corr = 0.0
    if 'delta_temperature_C' in event_df.columns and len(valid_cols) > 0:
        max_gas_curve = event_df[valid_cols].max(axis=1).values
        dt_curve = event_df['delta_temperature_C'].values
        if np.std(max_gas_curve) > 0 and np.std(dt_curve) > 0:
            cc = np.corrcoef(max_gas_curve, dt_curve)[0, 1]
            chem_therm_corr = cc if not np.isnan(cc) else 0.0
            
    n_above = 0
    for sensor in mq_cols:
        if sensor in event_df.columns:
            sig = event_df[sensor].values
            if len(sig) > 0:
                base = np.median(sig[:10]) if len(sig) >= 10 else np.median(sig)
                std = np.std(sig[:10]) if len(sig) >= 10 else np.std(sig)
                peak = np.max(sig)
                if peak > base + 3 * std:
                    n_above += 1
                    
    norm_gas = min(1.0, max_resp / 1000.0)
    norm_thermal = min(1.0, np.max(np.abs(event_df.get('delta_temperature_C', [0]))) / 10.0)
    norm_motion = min(1.0, np.max(event_df.get('motion_count', [0])) / 100.0)
    
    multimodal_anomaly_score = 0.4 * norm_gas + 0.3 * norm_thermal + 0.2 * norm_motion + 0.1 * corr
    
    return {
        'gas_correlation': np.nan_to_num(corr),
        'max_gas_response': np.nan_to_num(max_resp),
        'mean_gas_response': np.nan_to_num(mean_resp),
        'gas_response_variance': np.nan_to_num(var_resp),
        'chemical_thermal_agreement': np.nan_to_num(chem_therm_corr),
        'n_sensors_above_baseline': n_above,
        'multimodal_anomaly_score': np.nan_to_num(multimodal_anomaly_score)
    }

def extract_event_features(event_df, sampling_rate=10):
    features = {}
    gas_cols = ['mq1', 'mq2', 'mq3', 'mq4']
    gas_feats = {}
    for col in gas_cols:
        if col in event_df.columns:
            feats = extract_gas_features(event_df, col, sampling_rate)
            features.update(feats)
            gas_feats.update(feats)
            
    features.update(extract_thermal_features(event_df, sampling_rate))
    features.update(extract_environmental_features(event_df))
    features.update(extract_motion_features(event_df))
    features.update(extract_fusion_features(gas_feats, event_df))
    
    meta_cols = ['event_id', 'session_id', 'device_id', 'label', 'synthetic_condition', 
                 'anomaly_strength', 'environmental_condition', 'simulated_event_type']
    for col in meta_cols:
        if col in event_df.columns:
            features[col] = event_df[col].iloc[0]
            
    return features

def extract_all_features(raw_df):
    """Process all events."""
    if raw_df.empty:
        return pd.DataFrame()
        
    records = []
    grouped = raw_df.groupby('event_id')
    for event_id, event_df in grouped:
        feats = extract_event_features(event_df)
        records.append(feats)
        
    df_features = pd.DataFrame(records)
    
    meta_cols = ['event_id', 'session_id', 'device_id', 'label', 'synthetic_condition', 
                 'anomaly_strength', 'environmental_condition', 'simulated_event_type']
    cols = list(df_features.columns)
    for mc in meta_cols:
        if mc in cols:
            cols.remove(mc)
    ordered_cols = [mc for mc in meta_cols if mc in df_features.columns] + cols
    
    return df_features[ordered_cols]

if __name__ == '__main__':
    from preprocessing import preprocess_pipeline
    os.makedirs('data', exist_ok=True)
    df = preprocess_pipeline('data/raw_timeseries.csv')
    if not df.empty:
        features = extract_all_features(df)
        features.to_csv('data/feature_windows.csv', index=False)
        print(f'Extracted features for {len(features)} events')
        print(f'Feature columns: {len(features.columns)}')
        if 'label' in features.columns:
            print(f'Class distribution:\n{features.label.value_counts()}')
    else:
        print("No data to process.")
