
from rich.console import Console
from rich.panel import Panel
console = Console()
import os
import sys
import argparse
from datetime import datetime
import sqlite3
import pandas as pd
import yaml

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
    console.rule(style="dim cyan")
    console.print("CHECKING DEPENDENCIES")
    console.rule(style="dim cyan")
    
    config_path = os.path.join(PROJECT_ROOT, "config", "simulation_config.yaml")
    data_raw_dir = os.path.join(PROJECT_ROOT, "data", "raw")
    
    deps_ok = True
    
    if not os.path.exists(config_path):
        # Additional fallback check for config just in case
        fallback = os.path.join(CURRENT_SCRIPT_DIR, "simulation_config.yaml")
        if not os.path.exists(fallback):
            console.print(f"[ERROR] Configuration file not found at: {config_path}")
            deps_ok = False
        else:
            console.print(f"[bold green]OK[/bold green] Found config at fallback path: {fallback}")
    else:
        console.print(f"[bold green]OK[/bold green] Found config at: {config_path}")
        
    if not os.path.exists(data_raw_dir):
        console.print(f"[ERROR] Raw data directory not found at: {data_raw_dir}")
        deps_ok = False
    else:
        console.print(f"[bold green]OK[/bold green] Found raw data directory at: {data_raw_dir}")
        
    if not deps_ok:
        console.print("\n[HALT] Missing essential dependencies. Aborting pipeline.")
        sys.exit(1)
        
    console.print("[bold green]OK[/bold green] All essential dependencies found.")

def save_to_database(df, scenario_name):
    """Save the final DataFrame to SQLite database"""
    console.rule(style="dim cyan")
    console.print("SAVING RESULTS TO DATABASE")
    console.rule(style="dim cyan")
    
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
        console.print(f"[bold green]SUCCESS[/bold green] Appended {len(df)} records to database at:")
        console.print(f"   -> {db_path} (Table: recommendations)")
        
        conn.close()
    except Exception as e:
        console.print(f"[ERROR] Failed to save to database: {str(e)}")
        sys.exit(1)

def run_pipeline(scenario_name, skip_data_prep=False, clear_db=False):
    console.print("\n")
    console.print(Panel(f"[bold cyan]STARTING PIPELINE[/bold cyan]\nScenario: {scenario_name}", border_style="cyan"))
    
    # 1. Dependency Management
    check_dependencies()
    
    # Optional Database Clearance
    if clear_db:
        db_path = os.path.join(PROJECT_ROOT, "data", "processed", "recommendations.db")
        if os.path.exists(db_path):
            os.remove(db_path)
            console.print(f"\n[INFO] Cleared existing database at: {db_path}")
    
    # 2. Sequential Execution - Data Processing
    if not skip_data_prep:
        console.print("\n")
        console.print(Panel("[bold cyan]STEP 0: Running Data Processing (Cleaning & Preparation)[/bold cyan]", border_style="cyan"))
        dp_success = data_processing.run_data_processing()
        if not dp_success:
            console.print("\n" + "!"*60)
            console.print("[HALT] Data Processing failed.")
            console.print("Pipeline execution aborted.")
            console.print("!"*60)
            sys.exit(1)
        console.print("\n[bold green]SUCCESS[/bold green] Data Processing completed.")
    else:
        console.print("\n")
        console.print(Panel("[bold cyan]STEP 0: Skipped Data Processing (Data Prep)[/bold cyan]", border_style="cyan"))
        
    # 3. Sequential Execution - Simulation
    console.print("\n")
    console.print(Panel("[bold cyan]STEP 1: Running Physics Simulation[/bold cyan]", border_style="cyan"))
    sim_success = simulation.run_simulation()
    
    if not sim_success:
        console.print("\n" + "!"*60)
        console.print("[HALT] Simulation failed due to critical error (e.g., negative thermal threshold).")
        console.print("Pipeline execution aborted before ML analysis.")
        console.print("!"*60)
        sys.exit(1)
        
    console.print("\n[bold green]SUCCESS[/bold green] Simulation completed.")
    
    # 4. Sequential Execution - ML Analysis
    console.print("\n")
    console.print(Panel("[bold cyan]STEP 2: Running ML Clustering Analysis[/bold cyan]", border_style="cyan"))
    
    # Load config parameters to pass to ML Analysis for metadata
    config_params = {}
    config_path = os.path.join(PROJECT_ROOT, "config", "simulation_config.yaml")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            config_params = {
                'ambient_temp_c': float(config.get('environment', {}).get('ambient_temp_c', 25.0)),
                'risk_threshold_percent': float(config.get('simulation', {}).get('risk_threshold_percent', 1.0)),
                'n_interactions': int(config.get('simulation', {}).get('n_interactions', 10000)),
                'max_case_temp_c': float(config.get('heat_source', {}).get('max_case_temp_c', 105.0)),
                'heat_coefficient': float(config.get('heat_source', {}).get('heat_coefficient', 0.75))
            }
            
    df_final = ml_analysis.run_ml_analysis(scenario_name=scenario_name, config_params=config_params)
    
    if df_final is None or df_final.empty:
        console.print("\n" + "!"*60)
        console.print("[ERROR] ML Analysis failed to return data.")
        console.print("Pipeline execution aborted before saving.")
        console.print("!"*60)
        sys.exit(1)
        
    console.print("\n[bold green]SUCCESS[/bold green] ML Analysis completed.")
    
    
    # 4. Data Persistence & Metadata (Now handled internally by ml_analysis.py)
    console.print("\n[INFO] Data is now saved internally during ML Analysis step.")
    console.print("\n")
    console.print(Panel("[bold green]PIPELINE COMPLETED SUCCESSFULLY[/bold green]", border_style="green"))
    console.print("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orchestration Pipeline for TIM Cost Optimization")
    parser.add_argument('--scenario_name', type=str, required=True, help="Label to categorize environmental tests (e.g., 'Standard_25C')")
    parser.add_argument('--skip_data_prep', action='store_true', help="Skip data processing (Step 0) and use existing cost_data.csv")
    parser.add_argument('--clear_db', action='store_true', help="Clear existing recommendations.db before running the pipeline")
    
    args = parser.parse_args()
    
    run_pipeline(args.scenario_name, skip_data_prep=args.skip_data_prep, clear_db=args.clear_db)
