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

def run_ml_analysis(scenario_name="default"):
    print("\n" + "="*60)
    print("STARTING MACHINE LEARNING ANALYSIS V2.0")
    print("="*60)

    # -----------------------------------------------------
    # LOAD DATA (ALL 3 SCENARIOS)
    # -----------------------------------------------------
    heatsink_models = [
        'ModuleLED_Micro_8680',
        'ModuleLED_Micro_8560',
        'ModuleLED_Nano_7050'
    ]
    
    dfs = []
    for model in heatsink_models:
        filename = f"simu_results_{model}.csv"
        filepath = find_file(filename)
        
        if filepath:
            print(f"Loaded: {filename}")
            df_part = pd.read_csv(filepath)
            dfs.append(df_part)
        else:
            print(f"Warning: {filename} not found. Skipping.")

    if not dfs:
        print("Error: No simulation results found. Please run simulation.py first.")
        return None

    df_all = pd.concat(dfs, ignore_index=True)
    print(f"Total Data Points: {len(df_all)}")

    # -----------------------------------------------------
    # PREPARE FEATURES FOR MACHINE LEARNING
    # -----------------------------------------------------
    required_cols = ['cost_per_app', 'calculated_tim_r_cw', 'pass_probability_pct', 'max_t_case_99']
    for col in required_cols:
        if col not in df_all.columns:
            print(f"Error: Required column '{col}' missing. Check simulation.py output.")
            return None

    df_all['log_cost'] = np.log1p(df_all['cost_per_app']) 

    features = ['log_cost', 'calculated_tim_r_cw', 'pass_probability_pct', 'max_t_case_99']
    df_clean = df_all.dropna(subset=features).copy()
    X = df_clean[features].copy()
    
    # Scale Data
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Apply Weights (Safety dimensions get 2.0x multiplier)
    weights = np.array([1.0, 1.0, 2.0, 2.0])
    X_weighted = X_scaled * weights

    # -----------------------------------------------------
    # AUTO-K OPTIMIZATION (SILHOUETTE SCORE)
    # -----------------------------------------------------
    print("\nOptimizing Cluster Count (Auto-K)...")
    best_k = 4
    best_score = -1
    best_kmeans = None
    
    K_range = range(3, 9)
    for k in K_range:
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X_weighted)
        score = silhouette_score(X_weighted, labels)
        print(f"  K={k}: Silhouette Score = {score:.4f}")
        
        if score > best_score:
            best_score = score
            best_k = k
            best_kmeans = kmeans

    print(f"--> Selected Optimal K = {best_k} (Score: {best_score:.4f})")
    
    df_clean['cluster_id'] = best_kmeans.labels_

    # -----------------------------------------------------
    # RELATIVE CENTROID LABELING
    # -----------------------------------------------------
    centroids = df_clean.groupby('cluster_id')[['cost_per_app', 'calculated_tim_r_cw', 'pass_probability_pct']].mean()
    print("\n--- Cluster Centroids ---")
    print(centroids.round(2))

    cluster_labels = {}
    
    # Rank clusters by target metrics
    perf_ranks = centroids['calculated_tim_r_cw'].rank(method='min')
    cost_ranks = centroids['cost_per_app'].rank(method='min')
    tradeoff_scores = perf_ranks + cost_ranks

    for cid, row in centroids.iterrows():
        # Safety rule
        if row['pass_probability_pct'] < 99.0:
            cluster_labels[cid] = "❌ Avoid"
            
    # From remaining safe clusters, find Industrial and Best Value
    safe_cids = [cid for cid in centroids.index if cid not in cluster_labels]
    
    # Industrial: Best Performance (Lowest R_th)
    if safe_cids:
        industrial_cid = centroids.loc[safe_cids, 'calculated_tim_r_cw'].idxmin()
        cluster_labels[industrial_cid] = "🏭 Industrial"
        safe_cids.remove(industrial_cid)

    # Best Value: Best Tradeoff
    if safe_cids:
        best_value_cid = tradeoff_scores.loc[safe_cids].idxmin()
        cluster_labels[best_value_cid] = "🏆 Best Value"
        safe_cids.remove(best_value_cid)

    # Standard: Everything else
    for cid in safe_cids:
        cluster_labels[cid] = "✅ Standard"

    df_clean['recommendation_group'] = df_clean['cluster_id'].map(cluster_labels)

    # Hard-fallback Rule
    df_clean.loc[df_clean['pass_probability_pct'] < 99.0, 'recommendation_group'] = "❌ Avoid"

    # Merge back to df_all
    df_all = df_all.merge(df_clean[['tim_id', 'heatsink_model', 'recommendation_group']], 
                          on=['tim_id', 'heatsink_model'], how='left')
    df_all['recommendation_group'] = df_all['recommendation_group'].fillna("❌ Avoid")

    # -----------------------------------------------------
    # SQLITE DATABASE EXPORT
    # -----------------------------------------------------
    db_path = find_db_path()
    print(f"\nSaving results to Database: {db_path}")
    
    cols_order = [
         'recommendation_group', 
         'tim_id', 'mpn', 'manufacturer', 'description', 'type',
         'cost_per_app', 'calculated_tim_r_cw', 'pass_probability_pct',
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
        
        metadata = pd.DataFrame([{
            'run_timestamp': run_timestamp,
            'scenario_name': scenario_name,
            'algorithm': f'K-Means (Auto-K)',
            'optimal_k': best_k,
            'silhouette_score': float(best_score),
            'features': ', '.join(features),
            'records_processed': len(df_final)
        }])
        metadata.to_sql('run_metadata', conn, if_exists='append', index=False)
        
        conn.close()
        print("Database save successful.")
    except Exception as e:
        print(f"Error saving to database: {e}")

    # Show Summary
    print("\n=== Recommendation Summary ===")
    print(df_all['recommendation_group'].value_counts())
    
    return df_final

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run ML Analysis for TIM Recommendation')
    parser.add_argument('--scenario', type=str, default='default', help='Name of the scenario run')
    args = parser.parse_args()
    
    run_ml_analysis(scenario_name=args.scenario)