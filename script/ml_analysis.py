
from rich.console import Console
from rich.panel import Panel
console = Console()
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
import sqlite3
import datetime
import os
import sys
import argparse
import yaml

# -----------------------------------------------------
# SETUP PATHS
# -----------------------------------------------------
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_SCRIPT_DIR)

def find_file(filename, search_subdirs=['data/processed/simulation', 'data/processed', '../data/processed', '.']):
    if os.path.exists(filename): return filename
    for base in [CURRENT_SCRIPT_DIR, PROJECT_ROOT]:
        for sub in search_subdirs:
            path = os.path.join(base, sub, filename)
            if os.path.exists(path): return path
    return None

def find_db_path(dbname='recommendations.db'):
    db_path = os.path.join(PROJECT_ROOT, 'data', 'processed', dbname)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path

def run_ml_analysis(scenario_name="default", config_params=None):
    console.rule(style="dim cyan")
    console.print("STARTING MACHINE LEARNING ANALYSIS V2.0")
    console.rule(style="dim cyan")

    # -----------------------------------------------------
    # DYNAMIC CONFIGURATION (HEATSINKS & THRESHOLD)
    # -----------------------------------------------------
    config_path = find_file("simulation_config.yaml", search_subdirs=["config", "../config", "."])
    min_pass_pct = 99.0 # Default fallback
    heatsink_models = []
    
    if config_params and 'risk_threshold_percent' in config_params:
        risk_threshold = float(config_params['risk_threshold_percent'])
        min_pass_pct = 100.0 - risk_threshold
        console.print(f"Safety Threshold Loaded (from pipeline): Ranks with pass probability < {min_pass_pct}% will be removed.")
    
    if config_path:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
            # Fallback for risk_threshold if not passed from pipeline
            if not config_params or 'risk_threshold_percent' not in config_params:
                risk_threshold = float(config.get('simulation', {}).get('risk_threshold_percent', 1.0))
                min_pass_pct = 100.0 - risk_threshold
                console.print(f"Safety Threshold Loaded: Ranks with pass probability < {min_pass_pct}% will be removed.")
            
            # Extract heatsinks
            heatsinks = config.get('heatsinks', [])
            heatsink_models = [hs['model'].replace(" ", "_").replace(".", "") for hs in heatsinks]
            console.print(f"Loaded {len(heatsink_models)} expected heatsink models from config.")
            
    if not config_path and (not config_params or 'risk_threshold_percent' not in config_params):
        console.print(f"Warning: simulation_config.yaml not found. Using default cutoff {min_pass_pct}%")

    if not heatsink_models:
        console.print("Warning: Could not parse heatsinks from config. Using defaults.")
        heatsink_models = [
            'Micro_8680',
            'Micro_8560',
            'Nano_7050'
        ]

    # -----------------------------------------------------
    # LOAD DATA
    # -----------------------------------------------------
    
    dfs = []
    for model in heatsink_models:
        filename = f"simu_results_{model}.csv"
        filepath = find_file(filename)
        
        if filepath:
            console.print(f"Loaded: {filename}")
            df_part = pd.read_csv(filepath)
            dfs.append(df_part)
        else:
            console.print(f"Warning: {filename} not found. Skipping.")

    if not dfs:
        console.print("[bold red]Error:[/bold red] No simulation results found. Please run simulation.py first.")
        return None

    df_all = pd.concat(dfs, ignore_index=True)
    console.print(f"Total Data Points: {len(df_all)}")

    # -----------------------------------------------------
    # PREPARE FEATURES FOR MACHINE LEARNING
    # -----------------------------------------------------
    required_cols = ['cost_per_app', 'calculated_tim_r_cw', 'pass_probability_pct', 'max_t_case_99']
    for col in required_cols:
        if col not in df_all.columns:
            console.print(f"[bold red]Error:[/bold red] Required column '{col}' missing. Check simulation.py output.")
            return None

    # (Safety cutoff and config now loaded dynamically at the start of the function)

    # -----------------------------------------------------
    # STAGE 1: HARD SAFETY FILTER
    # -----------------------------------------------------
    df_all['recommendation_group'] = "Pending"
    unsafe_mask = df_all['pass_probability_pct'] < min_pass_pct
    df_all.loc[unsafe_mask, 'recommendation_group'] = "Avoid"
    
    df_safe = df_all[~unsafe_mask].dropna(subset=['cost_per_app', 'calculated_tim_r_cw', 'max_t_case_99']).copy()

    if len(df_safe) == 0:
        console.print(f"Warning: No TIMs passed the safety filter (>{min_pass_pct}%).")
        best_k = 0
        best_score = 0.0
        features = []
    else:
        console.print(f"Safe Data Points for ML: {len(df_safe)} / {len(df_all)}")

        # -----------------------------------------------------
        # STAGE 2: COMPETITIVE CLUSTERING
        # -----------------------------------------------------
        df_safe['log_cost'] = np.log1p(df_safe['cost_per_app']) 
        features = ['log_cost', 'calculated_tim_r_cw', 'max_t_case_99']
        
        # Scale Data (Per-Heatsink normalization to prevent large heatsinks from dominating)
        scaler = StandardScaler()
        X_scaled_df = pd.DataFrame(index=df_safe.index, columns=features)
        
        for hs in df_safe['heatsink_model'].unique():
            mask = df_safe['heatsink_model'] == hs
            if mask.sum() > 0:
                X_scaled_df.loc[mask, features] = scaler.fit_transform(df_safe.loc[mask, features])
                
        X_scaled = X_scaled_df.values.astype(float)

        # Apply Weights
        # log_cost: 1.5x, calculated_tim_r_cw: 1.5x, max_t_case_99: 1.0x
        weights = np.array([1.5, 1.5, 1.0])
        X_weighted = X_scaled * weights

        # -----------------------------------------------------
        # AUTO-K OPTIMIZATION (SILHOUETTE SCORE)
        # -----------------------------------------------------
        console.print("\nOptimizing Cluster Count (Auto-K)...")
        best_k = 3
        best_score = -1
        best_kmeans = None
        
        K_range = range(3, 6) # Try K=3, 4, 5
        for k in K_range:
            if len(X_weighted) < k:
                continue
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(X_weighted)
            score = silhouette_score(X_weighted, labels)
            console.print(f"  K={k}: Silhouette Score = {score:.4f}")
            
            if score > best_score:
                best_score = score
                best_k = k
                best_kmeans = kmeans

        if best_kmeans is not None:
            console.print(f"--> Selected Optimal K = {best_k} (Score: {best_score:.4f})")
            df_safe['cluster_id'] = best_kmeans.labels_

            # -----------------------------------------------------
            # DYNAMIC CENTROID RANKING
            # -----------------------------------------------------
            centroids = df_safe.groupby('cluster_id')[['cost_per_app', 'calculated_tim_r_cw']].mean()
            console.print("\n--- Safe Cluster Centroids ---")
            console.print(centroids.round(2))

            cluster_labels = {}
            
            # Rank clusters by target metrics
            perf_ranks = centroids['calculated_tim_r_cw'].rank(method='min')
            cost_ranks = centroids['cost_per_app'].rank(method='min')
            tradeoff_scores = perf_ranks + cost_ranks

            # Industrial: Best Performance (Lowest R_th)
            industrial_cid = centroids['calculated_tim_r_cw'].idxmin()
            cluster_labels[industrial_cid] = "Industrial"

            remaining_cids = [cid for cid in centroids.index if cid != industrial_cid]

            # Best Value: Best Tradeoff
            best_value_cid = None
            if remaining_cids:
                best_value_cid = tradeoff_scores.loc[remaining_cids].idxmin()
                cluster_labels[best_value_cid] = "Best Value"
                remaining_cids.remove(best_value_cid)

            # Standard: Everything else
            for cid in remaining_cids:
                cluster_labels[cid] = "Standard"

            df_safe['recommendation_group'] = df_safe['cluster_id'].map(cluster_labels)
            
            # Merge back to df_all (Match by index)
            df_all.loc[df_safe.index, 'recommendation_group'] = df_safe['recommendation_group']
        else:
            console.print("Warning: Not enough data points to cluster. Fallback to Standard.")
            df_all.loc[df_safe.index, 'recommendation_group'] = "Standard"
            
    df_all['recommendation_group'] = df_all['recommendation_group'].fillna("Avoid")

    # -----------------------------------------------------
    # SQLITE DATABASE EXPORT
    # -----------------------------------------------------
    db_path = find_db_path()
    console.print(f"\nSaving results to Database: {db_path}")
    
    cols_order = [
         'recommendation_group', 
         'tim_id', 'mpn', 'manufacturer', 'description', 'type',
         'cost_per_app', 'price_thb', 'calculated_tim_r_cw', 'pass_probability_pct',
         'max_t_case_99',
         'heatsink_model', 'heatsink_r_th',
         'reliability_status', 'avg_margin_cw',
         'k_wmk', 'thickness_mm'
    ]
    final_cols = [c for c in cols_order if c in df_all.columns] + [c for c in df_all.columns if c not in cols_order and c not in ['log_cost', 'cluster_id']]
    df_final = df_all[final_cols]

    run_timestamp = datetime.datetime.now().isoformat()
    df_final['run_timestamp'] = run_timestamp
    df_final['scenario_name'] = scenario_name

    try:
        conn = sqlite3.connect(db_path)
        df_final.to_sql('recommendations', conn, if_exists='append', index=False)
        
        metadata_dict = {
            'run_timestamp': run_timestamp,
            'scenario_name': scenario_name,
            'algorithm': f'K-Means (Auto-K)',
            'optimal_k': best_k,
            'silhouette_score': float(best_score),
            'features': ', '.join(features),
            'records_processed': len(df_final)
        }
        if config_params:
            metadata_dict.update(config_params)
            
        metadata = pd.DataFrame([metadata_dict])
        metadata.to_sql('run_metadata', conn, if_exists='append', index=False)
        
        conn.close()
        console.print("Database save successful.")
    except Exception as e:
        console.print(f"Error saving to database: {e}")

    # Show Summary
    console.print("\n=== Recommendation Summary ===")
    console.print(df_all['recommendation_group'].value_counts())
    
    return df_final

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run ML Analysis for TIM Recommendation')
    parser.add_argument('--scenario', type=str, default='default', help='Name of the scenario run')
    args = parser.parse_args()
    
    run_ml_analysis(scenario_name=args.scenario)