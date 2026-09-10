import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# DISCLAIMER: This is a SYNTHETIC dataset for ML pipeline development.
# This data does NOT represent real narcotics/explosives measurements.

# ---------------------------------------------------------
# 1. CONFIGURATION BLOCK
# ---------------------------------------------------------
OUTPUT_DIR = 'data'
PLOTS_DIR = 'plots'
SAMPLING_RATE = 10  # Hz
NUM_EVENTS = 2000

# Class distribution
CLASS_DIST = {
    'NORMAL': 0.60,
    'UNKNOWN': 0.25,
    'HIGH_RISK_SCREENING_EVENT': 0.15
}

np.random.seed(42)

# MQ sensor configs — each sensor is DIFFERENT
# Increased noise levels to prevent trivial classification
MQ_CONFIGS = {
    'mq1': {'baseline_range': (200, 400), 'sensitivity': 1.0, 'noise_std': 15, 'tau_rise': 1.5, 'tau_fall': 3.0, 'temp_coeff': 0.012, 'humidity_coeff': 0.008, 'spike_prob': 0.005, 'spike_amp': 60},
    'mq2': {'baseline_range': (300, 500), 'sensitivity': 0.7, 'noise_std': 20, 'tau_rise': 2.0, 'tau_fall': 4.0, 'temp_coeff': 0.018, 'humidity_coeff': 0.012, 'spike_prob': 0.006, 'spike_amp': 70},
    'mq3': {'baseline_range': (150, 350), 'sensitivity': 1.3, 'noise_std': 12, 'tau_rise': 1.0, 'tau_fall': 2.5, 'temp_coeff': 0.010, 'humidity_coeff': 0.006, 'spike_prob': 0.004, 'spike_amp': 55},
    'mq4': {'baseline_range': (250, 450), 'sensitivity': 0.85, 'noise_std': 18, 'tau_rise': 2.5, 'tau_fall': 5.0, 'temp_coeff': 0.015, 'humidity_coeff': 0.010, 'spike_prob': 0.005, 'spike_amp': 65}
}

# Platforms
PLATFORMS = {
    'PLT_SYNTH_001': {'name': 'SynthMumbai', 'lat': 19.0760, 'lon': 72.8777},
    'PLT_SYNTH_002': {'name': 'SynthDelhi', 'lat': 28.6139, 'lon': 77.2090},
    'PLT_SYNTH_003': {'name': 'SynthChennai', 'lat': 13.0827, 'lon': 80.2707},
    'PLT_SYNTH_004': {'name': 'SynthKolkata', 'lat': 22.5726, 'lon': 88.3639},
    'PLT_SYNTH_005': {'name': 'SynthBengaluru', 'lat': 12.9716, 'lon': 77.5946},
    'PLT_SYNTH_006': {'name': 'SynthLucknow', 'lat': 26.8467, 'lon': 80.9462},
    'PLT_SYNTH_007': {'name': 'SynthAhmedabad', 'lat': 23.0225, 'lon': 72.5714},
    'PLT_SYNTH_008': {'name': 'SynthHyderabad', 'lat': 17.3850, 'lon': 78.4867}
}

# Devices
DEVICE_IDS = [f'NARCOSCAN_DEV_{i:03d}' for i in range(1, 11)]

# Sub-conditions
CONDITIONS = {
    'NORMAL': ['empty_platform', 'passengers_walking', 'passengers_standing', 'crowded_platform', 'train_arriving', 'train_departing', 'locomotive_exhaust', 'food_stall', 'cleaning_activity', 'perfume_exposure', 'sanitizer_exposure', 'dust_change', 'temperature_drift', 'humidity_drift'],
    'UNKNOWN': ['weak_voc_response', 'partial_chemical_response', 'conflicting_sensor_response', 'strong_environmental_interference', 'sensor_drift', 'ambiguous_thermal', 'insufficient_agreement', 'unusual_crowd_interaction'],
    'HIGH_RISK_SCREENING_EVENT': ['strong_coordinated_voc_anomaly', 'rapid_gas_response', 'sustained_anomalous_response', 'gas_thermal_combined', 'chemical_motion_combined', 'multi_sensor_agreement']
}

# ---------------------------------------------------------
# 2. HELPER FUNCTIONS
# ---------------------------------------------------------
def generate_baseline_drift(n_samples, rate=0.5):
    """Slow random-walk baseline drift."""
    increments = np.random.normal(0, rate / np.sqrt(SAMPLING_RATE), n_samples)
    return np.cumsum(increments)

def generate_noise(n_samples, std, spike_prob=0.002, spike_amp=50):
    """Gaussian noise + occasional impulsive spikes."""
    gaussian = np.random.normal(0, std, n_samples)
    spikes = np.zeros(n_samples)
    spike_indices = np.random.random(n_samples) < spike_prob
    spikes[spike_indices] = np.random.choice([1, -1], size=np.sum(spike_indices)) * spike_amp
    return gaussian + spikes

def generate_response_curve(n_samples, onset_idx, amplitude, tau_rise, tau_fall, sampling_rate=10):
    """Sigmoid rise + exponential decay response curve."""
    time = np.arange(n_samples) / sampling_rate
    onset_time = onset_idx / sampling_rate
    response = np.zeros(n_samples)
    
    # Randomize response shape slightly
    tau_rise *= np.random.uniform(0.8, 1.2)
    tau_fall *= np.random.uniform(0.8, 1.2)
    
    for i in range(n_samples):
        t = time[i]
        if t >= onset_time:
            # We assume peak happens at onset_time + 3*tau_rise
            peak_time = onset_time + 3 * tau_rise
            if t < peak_time:
                response[i] = amplitude * (1 - np.exp(-(t - onset_time) / tau_rise))
            else:
                peak_amp = amplitude * (1 - np.exp(-(peak_time - onset_time) / tau_rise))
                response[i] = peak_amp * np.exp(-(t - peak_time) / tau_fall)
    
    return response

def generate_pir_signal(n_samples, activity_level):
    """Binary PIR motion signal."""
    pir = np.zeros(n_samples)
    trigger_prob = activity_level / SAMPLING_RATE
    for i in range(n_samples):
        if np.random.random() < trigger_prob:
            duration = np.random.randint(2, 6)
            pir[i:min(i + duration, n_samples)] = 1
    return pir

def generate_proximity(n_samples, base_distance, activity_level):
    """Proximity sensor in cm."""
    proximity = np.full(n_samples, base_distance, dtype=float)
    trigger_prob = activity_level / SAMPLING_RATE
    for i in range(n_samples):
        if np.random.random() < trigger_prob:
            duration = np.random.randint(10, 30)
            dip = np.random.uniform(20, 80)
            proximity[i:min(i + duration, n_samples)] = dip + np.random.normal(0, 2, min(i + duration, n_samples) - i)
    return proximity

# ---------------------------------------------------------
# 3. SESSION GENERATOR
# ---------------------------------------------------------
def generate_session(session_idx, event_labels):
    platform_id = np.random.choice(list(PLATFORMS.keys()))
    device_id = np.random.choice(DEVICE_IDS)
    
    ambient_temp = np.random.uniform(20, 42)
    humidity = np.random.uniform(30, 85)
    pressure = np.random.uniform(1005, 1020)
    
    if ambient_temp > 35 and humidity > 60:
        env_cond = 'hot_humid'
    elif ambient_temp > 35:
        env_cond = 'hot_dry'
    elif ambient_temp < 25 and humidity < 40:
        env_cond = 'cool_dry'
    else:
        env_cond = 'moderate'
        
    mq_baselines = {}
    for sensor, cfg in MQ_CONFIGS.items():
        mq_baselines[sensor] = np.random.uniform(cfg['baseline_range'][0], cfg['baseline_range'][1])
        
    return {
        'session_id': f'SES_{session_idx:04d}',
        'platform_id': platform_id,
        'device_id': device_id,
        'ambient_temp': ambient_temp,
        'humidity': humidity,
        'pressure': pressure,
        'env_cond': env_cond,
        **{f'{k}_baseline': v for k, v in mq_baselines.items()}
    }

# ---------------------------------------------------------
# 4. EVENT GENERATOR
# ---------------------------------------------------------
def generate_event(event_idx, label, condition, session_ctx):
    event_id = f'EVT_{event_idx:05d}'
    duration = np.random.uniform(10, 30)
    n_samples = int(duration * SAMPLING_RATE)
    
    # Base timestamp
    base_time = datetime(2023, 1, 1) + timedelta(minutes=event_idx * 5)
    timestamps = [base_time + timedelta(seconds=i/SAMPLING_RATE) for i in range(n_samples)]
    
    mq_baselines = {sensor: session_ctx[f'{sensor}_baseline'] + generate_baseline_drift(n_samples, rate=0.3) for sensor in MQ_CONFIGS}
    
    temp = session_ctx['ambient_temp'] + generate_baseline_drift(n_samples, rate=0.05) + generate_noise(n_samples, 0.3)
    humidity = session_ctx['humidity'] + generate_baseline_drift(n_samples, rate=0.1) + generate_noise(n_samples, 0.5)
    pressure = session_ctx['pressure'] + generate_baseline_drift(n_samples, rate=0.02) + generate_noise(n_samples, 0.2)
    
    for sensor in MQ_CONFIGS:
        temp_effect = (temp - 25) * MQ_CONFIGS[sensor]['temp_coeff'] * mq_baselines[sensor]
        humidity_effect = (humidity - 50) * MQ_CONFIGS[sensor]['humidity_coeff'] * mq_baselines[sensor]
        mq_baselines[sensor] += temp_effect + humidity_effect
        
    mq_signals = {}
    for sensor in ['mq1', 'mq2', 'mq3', 'mq4']:
        cfg = MQ_CONFIGS[sensor]
        signal = mq_baselines[sensor].copy()
        signal += generate_noise(n_samples, cfg['noise_std'], cfg['spike_prob'], cfg['spike_amp'])
        mq_signals[sensor] = signal

    anomaly_strength = 0.0
    onset_idx = int(np.random.uniform(0.1, 0.3) * n_samples)
    
    if label == 'NORMAL':
        anomaly_strength = np.random.uniform(0.0, 0.15)
        if condition == 'locomotive_exhaust':
            # Slow, broad MQ response primarily in MQ2 and MQ4 (combustion gases)
            # Can be quite strong — overlaps significantly with anomalies
            amp2 = np.random.uniform(150, 400)
            amp4 = np.random.uniform(120, 350)
            mq_signals['mq2'] += generate_response_curve(n_samples, onset_idx, amp2, 5.0, 8.0, SAMPLING_RATE)
            mq_signals['mq4'] += generate_response_curve(n_samples, onset_idx, amp4, 6.0, 9.0, SAMPLING_RATE)
            # Cross-sensitivity in MQ1 and MQ3
            mq_signals['mq1'] += generate_response_curve(n_samples, onset_idx, amp2 * np.random.uniform(0.1, 0.3), 6.0, 10.0, SAMPLING_RATE)
            mq_signals['mq3'] += generate_response_curve(n_samples, onset_idx, amp4 * np.random.uniform(0.05, 0.2), 7.0, 12.0, SAMPLING_RATE)
        elif condition == 'cleaning_activity':
            # Brief sharp spike in MQ1 and MQ3 (solvents/cleaning agents)
            # Can be strong enough to mimic anomaly
            amp1 = np.random.uniform(150, 350)
            amp3 = np.random.uniform(120, 300)
            mq_signals['mq1'] += generate_response_curve(n_samples, onset_idx, amp1, 0.5, 1.0, SAMPLING_RATE)
            mq_signals['mq3'] += generate_response_curve(n_samples, onset_idx, amp3, 0.7, 1.2, SAMPLING_RATE)
            # Minor cross-sensitivity
            mq_signals['mq2'] += generate_response_curve(n_samples, onset_idx, amp1 * np.random.uniform(0.05, 0.15), 1.0, 2.0, SAMPLING_RATE)
        elif condition == 'food_stall':
            # Sustained moderate elevation in MQ2, slow baseline shift
            amp2 = np.random.uniform(100, 300)
            mq_signals['mq2'] += generate_response_curve(n_samples, onset_idx, amp2, 10.0, 20.0, SAMPLING_RATE)
            mq_signals['mq4'] += generate_response_curve(n_samples, onset_idx, amp2 * np.random.uniform(0.2, 0.5), 12.0, 25.0, SAMPLING_RATE)
        elif condition == 'perfume_exposure':
            # Quick spike in MQ3 (alcohol-based) and minor MQ1 response
            amp3 = np.random.uniform(150, 400)
            mq_signals['mq3'] += generate_response_curve(n_samples, onset_idx, amp3, 0.8, 2.0, SAMPLING_RATE)
            mq_signals['mq1'] += generate_response_curve(n_samples, onset_idx, amp3 * np.random.uniform(0.15, 0.35), 1.0, 3.0, SAMPLING_RATE)
        elif condition == 'sanitizer_exposure':
            # Strong MQ3 response (alcohol), moderate MQ1 — can be very strong
            amp3 = np.random.uniform(200, 450)
            mq_signals['mq3'] += generate_response_curve(n_samples, onset_idx, amp3, 0.5, 1.5, SAMPLING_RATE)
            mq_signals['mq1'] += generate_response_curve(n_samples, onset_idx, amp3 * np.random.uniform(0.2, 0.45), 0.7, 2.0, SAMPLING_RATE)
            mq_signals['mq2'] += generate_response_curve(n_samples, onset_idx, amp3 * np.random.uniform(0.05, 0.15), 1.0, 3.0, SAMPLING_RATE)
        elif condition == 'dust_change':
            # Very minor, slow response across MQ2 and MQ4
            amp = np.random.uniform(30, 100)
            mq_signals['mq2'] += generate_response_curve(n_samples, onset_idx, amp, 8.0, 15.0, SAMPLING_RATE)
            mq_signals['mq4'] += generate_response_curve(n_samples, onset_idx, amp * 0.8, 10.0, 18.0, SAMPLING_RATE)
        elif condition == 'train_arriving' or condition == 'train_departing':
            # Brief exhaust + vibration, moderate MQ2/MQ4, quick onset/offset
            amp2 = np.random.uniform(50, 180)
            amp4 = np.random.uniform(40, 150)
            mq_signals['mq2'] += generate_response_curve(n_samples, onset_idx, amp2, 3.0, 5.0, SAMPLING_RATE)
            mq_signals['mq4'] += generate_response_curve(n_samples, onset_idx, amp4, 3.5, 6.0, SAMPLING_RATE)
        elif condition == 'crowded_platform':
            # Multiple small perfume/body odor spikes across sensors
            for _ in range(np.random.randint(1, 4)):
                s = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'])
                spike_onset = np.random.randint(0, max(1, n_samples - 20))
                amp = np.random.uniform(30, 120)
                mq_signals[s] += generate_response_curve(n_samples, spike_onset, amp, 1.0, 2.0, SAMPLING_RATE)
        # empty_platform, passengers_walking, passengers_standing, temperature_drift, humidity_drift
        # → just baseline noise + drift (already applied above)
            
    elif label == 'UNKNOWN':
        anomaly_strength = np.random.uniform(0.2, 0.6)
        if condition == 'weak_voc_response':
            # Only 1 sensor responds weakly — hard to distinguish from environmental
            sensor = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'])
            amp = np.random.uniform(150, 300)
            cfg = MQ_CONFIGS[sensor]
            mq_signals[sensor] += generate_response_curve(n_samples, onset_idx, amp, cfg['tau_rise'], cfg['tau_fall'], SAMPLING_RATE)
        elif condition == 'partial_chemical_response':
            # 2 sensors respond, but with different onset times (desynchronized)
            s1, s2 = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'], 2, replace=False)
            amp1 = np.random.uniform(200, 400)
            amp2 = np.random.uniform(100, 300)
            onset2 = onset_idx + int(np.random.uniform(2, 5) * SAMPLING_RATE)  # delayed
            mq_signals[s1] += generate_response_curve(n_samples, onset_idx, amp1, MQ_CONFIGS[s1]['tau_rise'], MQ_CONFIGS[s1]['tau_fall'], SAMPLING_RATE)
            mq_signals[s2] += generate_response_curve(n_samples, min(onset2, n_samples-1), amp2, MQ_CONFIGS[s2]['tau_rise'], MQ_CONFIGS[s2]['tau_fall'], SAMPLING_RATE)
        elif condition == 'conflicting_sensor_response':
            # 2 sensors respond but in opposite directions
            s1, s2 = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'], 2, replace=False)
            amp1 = np.random.uniform(200, 400)
            amp2 = -np.random.uniform(100, 200)
            mq_signals[s1] += generate_response_curve(n_samples, onset_idx, amp1, 2.0, 3.0, SAMPLING_RATE)
            mq_signals[s2] += generate_response_curve(n_samples, onset_idx, amp2, 2.0, 3.0, SAMPLING_RATE)
        elif condition == 'strong_environmental_interference':
            # All sensors drift up slowly (looks like response but is environmental)
            drift_amp = np.random.uniform(100, 300)
            for sensor in ['mq1', 'mq2', 'mq3', 'mq4']:
                mq_signals[sensor] += generate_response_curve(n_samples, 0, drift_amp * np.random.uniform(0.5, 1.0), 15.0, 30.0, SAMPLING_RATE)
        elif condition == 'sensor_drift':
            # One sensor drifts significantly, others stable
            sensor = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'])
            drift = np.linspace(0, np.random.uniform(150, 400), n_samples) + generate_noise(n_samples, 5)
            mq_signals[sensor] += drift
        elif condition == 'ambiguous_thermal':
            # Gas sensors show minor response, but thermal shows unusual delta
            sensor = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'])
            amp = np.random.uniform(100, 250)
            mq_signals[sensor] += generate_response_curve(n_samples, onset_idx, amp, MQ_CONFIGS[sensor]['tau_rise'], MQ_CONFIGS[sensor]['tau_fall'], SAMPLING_RATE)
        elif condition == 'insufficient_agreement':
            # 1 sensor responds strongly, others only faintly
            primary = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'])
            amp = np.random.uniform(250, 500)
            mq_signals[primary] += generate_response_curve(n_samples, onset_idx, amp, MQ_CONFIGS[primary]['tau_rise'], MQ_CONFIGS[primary]['tau_fall'], SAMPLING_RATE)
            for s in ['mq1', 'mq2', 'mq3', 'mq4']:
                if s != primary:
                    mq_signals[s] += generate_response_curve(n_samples, onset_idx, amp * np.random.uniform(0.05, 0.15), MQ_CONFIGS[s]['tau_rise'], MQ_CONFIGS[s]['tau_fall'], SAMPLING_RATE)
        elif condition == 'unusual_crowd_interaction':
            # Multiple sporadic responses from different sensors (crowd-induced)
            for _ in range(np.random.randint(2, 5)):
                s = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'])
                spike_onset = np.random.randint(0, max(1, n_samples - 20))
                amp = np.random.uniform(80, 250)
                mq_signals[s] += generate_response_curve(n_samples, spike_onset, amp, 1.0, 2.5, SAMPLING_RATE)
            
    elif label == 'HIGH_RISK_SCREENING_EVENT':
        anomaly_strength = np.random.uniform(0.5, 1.0)
        amp_base = np.random.uniform(150, 450)  # Reduced range for more overlap
        
        if condition == 'strong_coordinated_voc_anomaly':
            # 3-4 sensors respond with correlated onset (within 0.5s)
            n_responding = np.random.choice([3, 4], p=[0.3, 0.7])
            responding = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'], n_responding, replace=False)
            for sensor in responding:
                cfg = MQ_CONFIGS[sensor]
                onset = onset_idx + int(np.random.uniform(-0.5, 0.5) * SAMPLING_RATE)
                amp = amp_base * cfg['sensitivity'] * np.random.uniform(0.6, 1.2)
                mq_signals[sensor] += generate_response_curve(n_samples, max(0, onset), amp, cfg['tau_rise']*0.5, cfg['tau_fall']*1.5, SAMPLING_RATE)
        elif condition == 'rapid_gas_response':
            # Very sharp rise in 2-4 sensors
            n_responding = np.random.choice([2, 3, 4], p=[0.2, 0.5, 0.3])
            responding = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'], n_responding, replace=False)
            for sensor in responding:
                cfg = MQ_CONFIGS[sensor]
                amp = amp_base * cfg['sensitivity'] * np.random.uniform(0.5, 1.3)
                mq_signals[sensor] += generate_response_curve(n_samples, onset_idx, amp, cfg['tau_rise']*0.3, cfg['tau_fall'], SAMPLING_RATE)
        elif condition == 'sustained_anomalous_response':
            # 3-4 sensors rise and STAY elevated
            n_responding = np.random.choice([3, 4], p=[0.4, 0.6])
            responding = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'], n_responding, replace=False)
            for sensor in responding:
                cfg = MQ_CONFIGS[sensor]
                onset = onset_idx + int(np.random.uniform(-0.3, 0.3) * SAMPLING_RATE)
                amp = amp_base * cfg['sensitivity'] * np.random.uniform(0.5, 1.0)
                mq_signals[sensor] += generate_response_curve(n_samples, max(0, onset), amp, cfg['tau_rise'], cfg['tau_fall']*4.0, SAMPLING_RATE)
        elif condition == 'gas_thermal_combined':
            # 2-4 sensors respond AND thermal delta increases
            n_responding = np.random.choice([2, 3, 4], p=[0.2, 0.4, 0.4])
            responding = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'], n_responding, replace=False)
            for sensor in responding:
                cfg = MQ_CONFIGS[sensor]
                onset = onset_idx + int(np.random.uniform(-0.5, 0.5) * SAMPLING_RATE)
                amp = amp_base * cfg['sensitivity'] * np.random.uniform(0.5, 1.1)
                mq_signals[sensor] += generate_response_curve(n_samples, max(0, onset), amp, cfg['tau_rise']*0.6, cfg['tau_fall']*1.2, SAMPLING_RATE)
        elif condition == 'chemical_motion_combined':
            # 2-3 sensors respond + elevated PIR/proximity
            n_responding = np.random.choice([2, 3], p=[0.4, 0.6])
            responding = np.random.choice(['mq1', 'mq2', 'mq3', 'mq4'], n_responding, replace=False)
            for sensor in responding:
                cfg = MQ_CONFIGS[sensor]
                amp = amp_base * cfg['sensitivity'] * np.random.uniform(0.6, 1.2)
                mq_signals[sensor] += generate_response_curve(n_samples, onset_idx, amp, cfg['tau_rise']*0.5, cfg['tau_fall']*1.5, SAMPLING_RATE)
        elif condition == 'multi_sensor_agreement':
            # All 4 sensors respond with tight temporal synchronization
            shared_onset = onset_idx
            for sensor in ['mq1', 'mq2', 'mq3', 'mq4']:
                cfg = MQ_CONFIGS[sensor]
                onset = shared_onset + int(np.random.uniform(-0.2, 0.2) * SAMPLING_RATE)
                amp = amp_base * cfg['sensitivity'] * np.random.uniform(0.7, 1.1)
                mq_signals[sensor] += generate_response_curve(n_samples, max(0, onset), amp, cfg['tau_rise']*0.6, cfg['tau_fall']*1.0, SAMPLING_RATE)

    # Generate thermal signals
    target_temp = temp.copy()
    if label == 'NORMAL':
        delta_T = np.random.uniform(0, 5) + generate_noise(n_samples, 0.4)
    elif label == 'UNKNOWN':
        delta_T = np.random.uniform(0.5, 6) + generate_noise(n_samples, 0.5)
    elif label == 'HIGH_RISK_SCREENING_EVENT':
        delta_T = np.random.uniform(1, 8) + generate_noise(n_samples, 0.5)
        if condition == 'gas_thermal_combined':
            # Add thermal bump correlated with gas response
            delta_T += generate_response_curve(n_samples, onset_idx, np.random.uniform(1, 4), 2.0, 4.0, SAMPLING_RATE)
            
    target_temp = temp + delta_T
    
    # PIR and Proximity
    activity_level = 0.5
    if 'crowded' in condition or 'walking' in condition or 'train' in condition:
        activity_level = 2.0
    elif 'empty' in condition:
        activity_level = 0.1
    elif condition == 'chemical_motion_combined':
        activity_level = 3.0  # High activity correlated with chemical event
    elif 'standing' in condition:
        activity_level = 0.8
        
    pir = generate_pir_signal(n_samples, activity_level)
    proximity = generate_proximity(n_samples, np.random.uniform(150, 300), activity_level)
    motion_count = np.cumsum(np.concatenate(([0], np.diff(pir) > 0)))
    
    # Build dataframe
    df = pd.DataFrame({
        'timestamp': [t.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] for t in timestamps],
        'event_id': event_id,
        'session_id': session_ctx['session_id'],
        'device_id': session_ctx['device_id'],
        'platform_id': session_ctx['platform_id'],
        'latitude': PLATFORMS[session_ctx['platform_id']]['lat'],
        'longitude': PLATFORMS[session_ctx['platform_id']]['lon'],
        'mq1': mq_signals['mq1'],
        'mq2': mq_signals['mq2'],
        'mq3': mq_signals['mq3'],
        'mq4': mq_signals['mq4'],
        'target_temperature_C': target_temp,
        'ambient_temperature_C': temp,
        'delta_temperature_C': delta_T,
        'humidity_percent': humidity,
        'atmospheric_pressure_hPa': pressure,
        'pir_motion': pir,
        'proximity_cm': proximity,
        'motion_count': motion_count,
        'label': label,
        'synthetic_condition': condition,
        'anomaly_strength': anomaly_strength,
        'environmental_condition': session_ctx['env_cond'],
        'simulated_event_type': condition
    })
    
    # Add ~0.1% missing values
    for col in ['mq1', 'mq2', 'mq3', 'mq4', 'target_temperature_C', 'ambient_temperature_C', 'humidity_percent', 'atmospheric_pressure_hPa']:
        missing_mask = np.random.random(n_samples) < 0.001
        df.loc[missing_mask, col] = np.nan
        
    return df

# ---------------------------------------------------------
# 5. MAIN GENERATION LOOP
# ---------------------------------------------------------
def print_dataset_statistics(df):
    print("\\nDataset Statistics:")
    print(f"Total Rows: {len(df)}")
    print(f"Total Events: {df['event_id'].nunique()}")
    print(f"Total Sessions: {df['session_id'].nunique()}")
    
    event_labels = df.groupby('event_id').first()['label']
    print("\\nClass Distribution (Events):")
    print(event_labels.value_counts(normalize=True))
    
    print("\\nMissing Values:")
    print(df.isnull().sum())

def generate_quality_plots(df):
    print("Generating quality plots...")
    event_df = df.groupby('event_id').first()
    
    # 1. Class Distribution
    plt.figure(figsize=(8, 5))
    sns.countplot(data=event_df, x='label', order=['NORMAL', 'UNKNOWN', 'HIGH_RISK_SCREENING_EVENT'])
    plt.title('Event Class Distribution')
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'class_distribution.png'))
    plt.close()
    
    # 2. Example gas response curves
    for label in ['NORMAL', 'UNKNOWN', 'HIGH_RISK_SCREENING_EVENT']:
        sample_events = event_df[event_df['label'] == label].index[:3]
        if len(sample_events) > 0:
            plt.figure(figsize=(15, 10))
            for i, ev_id in enumerate(sample_events):
                plt.subplot(3, 1, i+1)
                ev_data = df[df['event_id'] == ev_id]
                for mq in ['mq1', 'mq2', 'mq3', 'mq4']:
                    plt.plot(range(len(ev_data)), ev_data[mq], label=mq)
                plt.title(f'{label} Example - {ev_id} ({ev_data["synthetic_condition"].iloc[0]})')
                plt.legend()
            plt.tight_layout()
            plt.savefig(os.path.join(PLOTS_DIR, f'example_{label.lower()}_responses.png'))
            plt.close()
            
    # 3. Environmental Drift across sessions (MQ1 baseline)
    plt.figure(figsize=(12, 6))
    session_mq1 = df.groupby('session_id')['mq1'].mean().reset_index()
    # Sort for better visualization
    plt.plot(session_mq1['session_id'].str[-4:].astype(int), session_mq1['mq1'], 'o-')
    plt.title('MQ1 Baseline Variation Across Sessions')
    plt.xlabel('Session Index')
    plt.ylabel('Mean MQ1 Value')
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'mq1_session_drift.png'))
    plt.close()

    # 4. Sensor correlation heatmap
    plt.figure(figsize=(8, 6))
    sns.heatmap(df[['mq1', 'mq2', 'mq3', 'mq4', 'target_temperature_C', 'humidity_percent']].corr(), annot=True, cmap='coolwarm')
    plt.title('Sensor Correlation Heatmap')
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'sensor_correlation.png'))
    plt.close()

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(PLOTS_DIR, exist_ok=True)
    
    sessions = []
    event_idx = 0
    session_idx = 0
    
    # Generate label list to maintain proportions
    labels_pool = (['NORMAL'] * int(NUM_EVENTS * CLASS_DIST['NORMAL']) + 
                   ['UNKNOWN'] * int(NUM_EVENTS * CLASS_DIST['UNKNOWN']) + 
                   ['HIGH_RISK_SCREENING_EVENT'] * int(NUM_EVENTS * CLASS_DIST['HIGH_RISK_SCREENING_EVENT']))
    np.random.shuffle(labels_pool)
    
    while event_idx < NUM_EVENTS:
        n_events = np.random.randint(5, 16)
        if event_idx + n_events > NUM_EVENTS:
            n_events = NUM_EVENTS - event_idx
        
        session_labels = labels_pool[event_idx:event_idx+n_events]
        sessions.append((session_idx, session_labels))
        session_idx += 1
        event_idx += n_events
        
    all_rows = []
    event_counter = 0
    print("Starting generation...")
    for s_idx, labels in sessions:
        session_ctx = generate_session(s_idx, labels)
        for label in labels:
            condition = np.random.choice(CONDITIONS[label])
            event_df = generate_event(event_counter, label, condition, session_ctx)
            all_rows.append(event_df)
            event_counter += 1
            if event_counter % 100 == 0:
                print(f"Generated {event_counter}/{NUM_EVENTS} events...")
                
    df = pd.concat(all_rows, ignore_index=True)
    out_path = os.path.join(OUTPUT_DIR, 'raw_timeseries.csv')
    df.to_csv(out_path, index=False)
    print(f"Dataset saved to {out_path}")
    
    print_dataset_statistics(df)
    generate_quality_plots(df)

if __name__ == '__main__':
    main()
