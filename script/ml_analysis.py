import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import os
import sys

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

def run_ml_analysis():
    print("\n" + "="*60)
    print("STARTING MACHINE LEARNING ANALYSIS (K-MEANS)")
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
        # Construct filename like: simulation_results_ModuleLED_Micro_8680.csv
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
        return

    df_all = pd.concat(dfs, ignore_index=True)
    print(f"Total Data Points: {len(df_all)}")

    # -----------------------------------------------------
    # PREPARE FEATURES FOR MACHINE LEARNING
    # -----------------------------------------------------
    # 2 main factors for clustering: "Cost" and "Performance" (R_th)
    # Use Log Transform with price because the price range is wide
    df_all['log_cost'] = np.log1p(df_all['cost_per_app']) 

    features = ['log_cost', 'calculated_tim_r_cw']
    X = df_all[features].dropna()
    
    # Scale Data
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # -----------------------------------------------------
    # RUN K-MEANS CLUSTERING
    # -----------------------------------------------------
    print("Running K-Means (4 Clusters)...")
    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    df_all.loc[X.index, 'cluster_id'] = kmeans.fit_predict(X_scaled)

    # -----------------------------------------------------
    # AUTO-LABELING (RULE-BASED LABELING)
    # -----------------------------------------------------
    # Find centroids of each cluster
    centroids = df_all.groupby('cluster_id')[['cost_per_app', 'calculated_tim_r_cw']].mean()
    print("\n--- Cluster Centroids ---")
    print(centroids)

    # Logic for Naming Groups (Rule-based labeling)
    labels = {}
    for cid, row in centroids.iterrows():
        cost = row['cost_per_app']
        perf = row['calculated_tim_r_cw']
        
        if cost < 50 and perf < 0.2:
            label = "🏆 Best Value"
        elif cost > 1000 and perf < 0.1:
            label = "🏭 Industrial"
        elif perf > 0.8:
            label = "❌ Avoid"
        else:
            label = "✅ Standard"
        labels[cid] = label

    df_all['recommendation_group'] = df_all['cluster_id'].map(labels)

    # Save to the same folder as input
    output_dir = os.path.dirname(find_file(f"simu_results_{heatsink_models[0]}.csv"))
    output_path = os.path.join(output_dir, 'final_recommendation_data.csv')
    
    # Remove internal columns for cleaner Power BI data
    df_final = df_all.drop(columns=['log_cost', 'cluster_id'])
    
    # Reorder columns for Final Recommendation
    cols_order = [
         'recommendation_group', 
         'tim_id', 'mpn', 'manufacturer', 'description', 'type',
         'cost_per_app', 'calculated_tim_r_cw', 'pass_probability_pct',
         'heatsink_model', 'heatsink_r_th',
         'reliability_status', 'avg_margin_cw',
         'k_wmk', 'thickness_mm'
    ]
    final_cols = [c for c in cols_order if c in df_final.columns] + [c for c in df_final.columns if c not in cols_order]
    df_final = df_final[final_cols]
    
    df_final.to_csv(output_path, index=False)
    print(f"\nFinal Data Saved: {output_path}")
    
    # Show Summary
    print("\n=== Recommendation Summary ===")
    print(df_all['recommendation_group'].value_counts())

if __name__ == "__main__":
    run_ml_analysis()