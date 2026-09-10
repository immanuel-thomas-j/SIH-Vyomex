import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

# DISCLAIMER: This is a SYNTHETIC dataset for ML pipeline development.
# This data does NOT represent real narcotics/explosives measurements.

def split_dataset(input_file, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Loading data from {input_file}...")
    df = pd.read_csv(input_file)
    
    if 'session_id' not in df.columns or 'label' not in df.columns:
        raise ValueError("Missing required columns: session_id or label")
        
    print(f"Total events: {len(df)}")
    
    # Determine dominant label per session for stratified split
    session_labels = df.groupby('session_id')['label'].agg(lambda x: x.mode()[0]).reset_index()
    print(f"Total unique sessions: {len(session_labels)}")
    
    # First split: 70% train, 30% temp
    train_sessions, temp_sessions = train_test_split(
        session_labels['session_id'], 
        test_size=0.3, 
        stratify=session_labels['label'],
        random_state=42
    )
    
    # Second split: val/test from temp — use stratification if possible, fallback otherwise
    temp_labels = session_labels[session_labels['session_id'].isin(temp_sessions)]
    try:
        val_sessions, test_sessions = train_test_split(
            temp_labels['session_id'],
            test_size=0.5,
            stratify=temp_labels['label'],
            random_state=42
        )
    except ValueError:
        # Not enough members in some class for stratified split — fall back
        print("Warning: Falling back to non-stratified val/test split (too few sessions per class)")
        val_sessions, test_sessions = train_test_split(
            temp_labels['session_id'],
            test_size=0.5,
            random_state=42
        )
    
    train_df = df[df['session_id'].isin(train_sessions)]
    val_df = df[df['session_id'].isin(val_sessions)]
    test_df = df[df['session_id'].isin(test_sessions)]
    
    # Verify disjoint sets
    assert len(set(train_df['session_id']).intersection(set(val_df['session_id']))) == 0, "Session leak: train/val"
    assert len(set(train_df['session_id']).intersection(set(test_df['session_id']))) == 0, "Session leak: train/test"
    assert len(set(val_df['session_id']).intersection(set(test_df['session_id']))) == 0, "Session leak: val/test"
    
    # Save files
    train_df.to_csv(os.path.join(output_dir, 'train.csv'), index=False)
    val_df.to_csv(os.path.join(output_dir, 'validation.csv'), index=False)
    test_df.to_csv(os.path.join(output_dir, 'test.csv'), index=False)
    
    print("\n=== Split Statistics ===")
    for name, split_df in zip(['Train', 'Validation', 'Test'], [train_df, val_df, test_df]):
        print(f"{name}: {len(split_df)} events, {split_df['session_id'].nunique()} sessions")
        print("Class distribution:")
        print(split_df['label'].value_counts(normalize=True))
        print("-" * 30)
        
if __name__ == '__main__':
    split_dataset('data/feature_windows.csv', 'data')
