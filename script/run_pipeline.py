import os
import sys
import argparse
from datetime import datetime
import sqlite3
import pandas as pd

import data_processing
import simulation
import ml_analysis

# -----------------------------------------------------
# SETUP PATHS
# -----------------------------------------------------
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_SCRIPT_DIR)

def check_dependencies():
    """Verify that necessary configuration and raw data directories exist"""
    print("\n" + "="*60)
    print("CHECKING DEPENDENCIES")
    print("="*60)
    
    config_path = os.path.join(PROJECT_ROOT, "config", "simulation_config.yaml")
    data_raw_dir = os.path.join(PROJECT_ROOT, "data", "raw")
    
    deps_ok = True
    
    if not os.path.exists(config_path):
        # Additional fallback check for config just in case
        fallback = os.path.join(CURRENT_SCRIPT_DIR, "simulation_config.yaml")
        if not os.path.exists(fallback):
            print(f"[ERROR] Configuration file not found at: {config_path}")
            deps_ok = False
        else:
            print(f"[OK] Found config at fallback path: {fallback}")
    else:
        print(f"[OK] Found config at: {config_path}")
        
    if not os.path.exists(data_raw_dir):
        print(f"[ERROR] Raw data directory not found at: {data_raw_dir}")
        deps_ok = False
    else:
        print(f"[OK] Found raw data directory at: {data_raw_dir}")
        
    if not deps_ok:
        print("\n[HALT] Missing essential dependencies. Aborting pipeline.")
        sys.exit(1)
        
    print("[OK] All essential dependencies found.")

def save_to_database(df, scenario_name):
    """Save the final DataFrame to SQLite database"""
    print("\n" + "="*60)
    print("SAVING RESULTS TO DATABASE")
    print("="*60)
    
    processed_dir = os.path.join(PROJECT_ROOT, "data", "processed")
    os.makedirs(processed_dir, exist_ok=True)
    
    db_path = os.path.join(processed_dir, "recommendations.db")
    
    # Inject Metadata
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df['scenario_name'] = scenario_name
    df['run_timestamp'] = current_time
    
    # Connect to SQLite and append data
    try:
        conn = sqlite3.connect(db_path)
        
        # use if_exists='append' for non-destructive storage
        df.to_sql('recommendations', conn, if_exists='append', index=False)
        print(f"[SUCCESS] Appended {len(df)} records to database at:")
        print(f"   -> {db_path} (Table: recommendations)")
        
        conn.close()
    except Exception as e:
        print(f"[ERROR] Failed to save to database: {str(e)}")
        sys.exit(1)

def run_pipeline(scenario_name, skip_data_prep=False):
    print("\n" + "#"*60)
    print(f"STARTING ANTIGRAVITY ORCHESTRATION PIPELINE")
    print(f"Scenario: {scenario_name}")
    print("#"*60)
    
    # 1. Dependency Management
    check_dependencies()
    
    # 2. Sequential Execution - Data Processing
    if not skip_data_prep:
        print("\n>>> STEP 0: Running Data Processing (Cleaning & Preparation) >>>")
        dp_success = data_processing.run_data_processing()
        if not dp_success:
            print("\n" + "!"*60)
            print("[HALT] Data Processing failed.")
            print("Pipeline execution aborted.")
            print("!"*60)
            sys.exit(1)
        print("\n[SUCCESS] Data Processing completed.")
    else:
        print("\n>>> STEP 0: Skipped Data Processing (Data Prep) >>>")
        
    # 3. Sequential Execution - Simulation
    print("\n>>> STEP 1: Running Physics Simulation >>>")
    sim_success = simulation.run_simulation()
    
    if not sim_success:
        print("\n" + "!"*60)
        print("[HALT] Simulation failed due to critical error (e.g., negative thermal threshold).")
        print("Pipeline execution aborted before ML analysis.")
        print("!"*60)
        sys.exit(1)
        
    print("\n[SUCCESS] Simulation completed.")
    
    # 4. Sequential Execution - ML Analysis
    print("\n>>> STEP 2: Running ML Clustering Analysis >>>")
    df_final = ml_analysis.run_ml_analysis()
    
    if df_final is None or df_final.empty:
        print("\n" + "!"*60)
        print("[ERROR] ML Analysis failed to return data.")
        print("Pipeline execution aborted before saving.")
        print("!"*60)
        sys.exit(1)
        
    print("\n[SUCCESS] ML Analysis completed.")
    
    
    # 4. Data Persistence & Metadata (Now handled internally by ml_analysis.py)
    print("\n[INFO] Data is now saved internally during ML Analysis step.")
    print("\n" + "#"*60)
    print("PIPELINE COMPLETED SUCCESSFULLY")
    print("#"*60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orchestration Pipeline for TIM Cost Optimization")
    parser.add_argument('--scenario_name', type=str, required=True, help="Label to categorize environmental tests (e.g., 'Standard_25C')")
    parser.add_argument('--skip_data_prep', action='store_true', help="Skip data processing (Step 0) and use existing cost_data.csv")
    
    args = parser.parse_args()
    
    run_pipeline(args.scenario_name, skip_data_prep=args.skip_data_prep)
