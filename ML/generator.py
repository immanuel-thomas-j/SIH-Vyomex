# Dashboard generator
import json, os, pandas as pd

with open('data/dashboard_data.json', 'r', encoding='utf-8') as f:
    d1 = json.load(f)

with open('data/full_dashboard_data.json', 'r', encoding='utf-8') as f:
    d2 = json.load(f)

df_raw = pd.read_csv('data/raw_timeseries.csv')

all_events = {}
for eid, ev in d2.get('events', {}).items():
    all_events[eid] = ev

for r in d2.get('table', []):
    eid = r['event_id']
    if eid not in all_events:
        sub = df_raw[df_raw['event_id'] == eid].sort_values('timestamp')
        if len(sub) > 0:
            first = sub.iloc[0]
            all_events[eid] = {
                'event_id': eid,
                'label': str(r['label']),
                'condition': str(r['condition']),
                'display_name': str(r['condition']).replace('_', ' ').title(),
                'session_id': str(first['session_id']),
                'device_id': str(first['device_id']),
                'platform_id': str(first['platform_id']),
                'multimodal_score': float(r['score']),
                'gas_correlation': float(r['corr']),
                'max_gas_response': float(r['max_gas']),
                'deltaT_max': float(r['deltaT']),
                'mq1_peak': float(sub['mq1'].max()),
                'mq2_peak': float(sub['mq2'].max()),
                'mq3_peak': float(sub['mq3'].max()),
                'mq4_peak': float(sub['mq4'].max()),
                'mq1': [round(x, 2) for x in sub['mq1'].tolist()],
                'mq2': [round(x, 2) for x in sub['mq2'].tolist()],
                'mq3': [round(x, 2) for x in sub['mq3'].tolist()],
                'mq4': [round(x, 2) for x in sub['mq4'].tolist()],
                'delta_T': [round(x, 2) for x in sub['delta_temperature_C'].tolist()],
                'target_temp': [round(x, 2) for x in sub['target_temperature_C'].tolist()],
                'ambient_temp': [round(x, 2) for x in sub['ambient_temperature_C'].tolist()],
                'humidity': [round(x, 2) for x in sub['humidity_percent'].tolist()],
                'pressure': [round(x, 2) for x in sub['atmospheric_pressure_hPa'].tolist()],
                'pir': [int(x) for x in sub['pir_motion'].tolist()],
                'proximity': [round(x, 2) for x in sub['proximity_cm'].tolist()]
            }

embedded_data = {
    'events': all_events,
    'table': d2.get('table', []),
    'top_features': d1.get('top_features', []),
    'confusion_matrices': d1.get('confusion_matrices', {}),
    'stats': d1.get('stats', {})
}

with open('embedded_data.json', 'w', encoding='utf-8') as f:
    json.dump(embedded_data, f, separators=(',', ':'))

print('embedded_data.json created successfully!')
