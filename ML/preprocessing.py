"""
Data loading and cleaning utility for NARCOSCAN synthetic dataset.
DISCLAIMER: This data is SYNTHETIC and DOES NOT represent real narcotics/explosives measurements.
"""
import os
import logging
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_raw_data(filepath='data/raw_timeseries.csv'):
    """Load CSV, parse timestamps, validate columns."""
    logger.info(f"Loading data from {filepath}")
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    expected_cols = [
        'timestamp', 'event_id', 'session_id', 'device_id', 'platform_id', 
        'latitude', 'longitude', 'mq1', 'mq2', 'mq3', 'mq4', 
        'target_temperature_C', 'ambient_temperature_C', 'delta_temperature_C', 
        'humidity_percent', 'atmospheric_pressure_hPa', 'pir_motion', 
        'proximity_cm', 'motion_count', 'label', 'synthetic_condition', 
        'anomaly_strength', 'environmental_condition', 'simulated_event_type'
    ]
    missing = set(expected_cols) - set(df.columns)
    if missing:
        logger.warning(f"Missing columns: {missing}")
    return df

def validate_physical_bounds(df):
    """Check and clip physical bounds for sensors."""
    df_clean = df.copy()
    
    mq_cols = ['mq1', 'mq2', 'mq3', 'mq4']
    for col in mq_cols:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].clip(lower=0, upper=1500)
            
    if 'target_temperature_C' in df_clean.columns:
        df_clean['target_temperature_C'] = df_clean['target_temperature_C'].clip(lower=-10, upper=60)
    if 'ambient_temperature_C' in df_clean.columns:
        df_clean['ambient_temperature_C'] = df_clean['ambient_temperature_C'].clip(lower=-10, upper=60)
        
    if 'humidity_percent' in df_clean.columns:
        df_clean['humidity_percent'] = df_clean['humidity_percent'].clip(lower=0, upper=100)
        
    if 'atmospheric_pressure_hPa' in df_clean.columns:
        df_clean['atmospheric_pressure_hPa'] = df_clean['atmospheric_pressure_hPa'].clip(lower=900, upper=1100)
        
    return df_clean

def handle_missing_values(df):
    """Forward-fill within each event_id group."""
    df_clean = df.copy()
    # Sort to ensure proper ordering within events
    df_clean = df_clean.sort_values(['event_id', 'timestamp']).reset_index(drop=True)
    
    # Forward-fill and back-fill within each event group
    sensor_cols = ['mq1', 'mq2', 'mq3', 'mq4', 'target_temperature_C', 
                   'ambient_temperature_C', 'humidity_percent', 'atmospheric_pressure_hPa']
    for col in sensor_cols:
        if col in df_clean.columns:
            df_clean[col] = df_clean.groupby('event_id')[col].transform(
                lambda x: x.ffill().bfill()
            )
    
    remaining_nan = df_clean[sensor_cols].isna().sum().sum()
    if remaining_nan > 0:
        logger.warning(f"{remaining_nan} NaN values remain after fill.")
    return df_clean

def estimate_baselines(df):
    """Estimate baseline as median of first 10 samples (first 1 second) for each event."""
    df_out = df.copy()
    
    for col in ['mq1', 'mq2', 'mq3', 'mq4']:
        if col in df_out.columns:
            # Calculate per-event baselines using first 10 samples
            baselines = df_out.groupby('event_id')[col].transform(
                lambda x: x.head(10).median() if len(x) >= 10 else x.median()
            )
            df_out[f'{col}_baseline_est'] = baselines
    
    return df_out

def preprocess_pipeline(filepath='data/raw_timeseries.csv'):
    """Full pipeline: load -> validate -> handle_missing -> estimate_baselines"""
    if not os.path.exists(filepath):
        logger.error(f"File {filepath} not found.")
        return pd.DataFrame()
        
    df = load_raw_data(filepath)
    df = validate_physical_bounds(df)
    df = handle_missing_values(df)
    df = estimate_baselines(df)
    logger.info(f"Preprocessed {len(df)} rows")
    return df

if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    filepath = 'data/raw_timeseries.csv'
    if os.path.exists(filepath):
        df = preprocess_pipeline(filepath)
        print(f'Preprocessed {len(df)} rows, {df.event_id.nunique()} events')
        df.to_csv('data/raw_timeseries_cleaned.csv', index=False)
    else:
        print(f"Skipping preprocessing: {filepath} not found.")
