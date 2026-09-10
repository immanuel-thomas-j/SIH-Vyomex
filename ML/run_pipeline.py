"""
Master execution script for NARCOSCAN end-to-end synthetic dataset and ML pipeline.
Smart India Hackathon Prototype: NARCOSCAN
"""

import os
import sys
import time
import subprocess

def run_step(step_num, title, script_name):
    print(f"\n{'='*70}")
    print(f" [STEP {step_num}/5] {title.upper()}")
    print(f" Running: python {script_name}")
    print(f"{'='*70}")
    start_time = time.time()
    
    cmd = [sys.executable, script_name]
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    elapsed = time.time() - start_time
    if result.returncode != 0:
        print(f"\n[ERROR] Step {step_num} failed with return code {result.returncode} ({elapsed:.1f}s)")
        sys.exit(result.returncode)
    else:
        print(f"\n[SUCCESS] Step {step_num} completed in {elapsed:.1f}s")

def main():
    print("*" * 70)
    print(" NARCOSCAN: Context-Aware Multimodal Narcotics Screening")
    print(" & Railway Threat Intelligence System — ML Pipeline Runner")
    print("*" * 70)
    print(" DISCLAIMER: Synthetic development dataset for ML pipeline validation.")
    print(" Does NOT represent real chemical signatures of narcotics/explosives.")
    print("*" * 70)
    
    os.makedirs("data", exist_ok=True)
    os.makedirs("plots", exist_ok=True)
    
    total_start = time.time()
    
    # Step 1: Raw dataset generation
    run_step(1, "Synthetic Multimodal Time-Series Generation", "generate_dataset.py")
    
    # Step 2: Preprocessing & Feature Extraction
    run_step(2, "Feature Engineering & Spectral Extraction", "feature_extraction.py")
    
    # Step 3: Session-Disjoint Dataset Splitting
    run_step(3, "Session-Grouped Stratified Dataset Splitting", "split_dataset.py")
    
    # Step 4: Baseline Model Training
    run_step(4, "Baseline Classifier Training (Rule-Based, LR, RF)", "train_baseline.py")
    
    # Step 5: Evaluation & Report
    run_step(5, "Model Evaluation, Confusion Matrices & Trade-Off Analysis", "evaluate.py")
    
    total_elapsed = time.time() - total_start
    print(f"\n{'#'*70}")
    print(f" ALL 5 PIPELINE STAGES COMPLETED SUCCESSFULLY IN {total_elapsed:.1f}s!")
    print(f" Output files saved to 'data/' and 'plots/'")
    print(f"{'#'*70}\n")

if __name__ == "__main__":
    main()
