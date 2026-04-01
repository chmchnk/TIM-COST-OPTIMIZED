
from rich.console import Console
from rich.panel import Panel
console = Console()
import pandas as pd
import numpy as np
import yaml
import math
import os
import sys
import thermal_model as tm
from tqdm import tqdm

# -----------------------------------------------------
# SETUP PATHS 
# -----------------------------------------------------
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_SCRIPT_DIR)

def find_file(filename, search_subdirs=['config', 'data', 'data/processed', '..', '.']):
    if os.path.exists(filename): return filename
    search_bases = [CURRENT_SCRIPT_DIR, PROJECT_ROOT]
    for base in search_bases:
        for sub in search_subdirs:
            full_path = os.path.join(base, sub, filename)
            if os.path.exists(full_path): return os.path.normpath(full_path)
    return None

def load_config(config_name='simulation_config.yaml'):
    config_path = find_file(config_name)
    if config_path:
        console.print(f"Found Config at: {config_path}")
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    else:
        console.print(f"[bold red]Error:[/bold red] Config file '{config_name}' not found")
        sys.exit(1)

# -----------------------------------------------------
# MONTECARLO SIMULATION (MULTI-HEATSINK MODE)
# -----------------------------------------------------
def run_simulation(data_name='cost_data.csv', config_name='simulation_config.yaml'):
    console.rule(style="dim cyan")
    console.print("INITIALIZING MULTI-SCENARIO SIMULATION")
    console.rule(style="dim cyan")
    
    config = load_config(config_name)
    
    # Extract config parameters
    try:
        SIM_PARAMS = config['simulation']
        ENV_PARAMS = config['environment']
        LED_PARAMS = config['heat_source']
        UNCERTAINTIES = config['uncertainties']
        HEATSINK_LIST = config['heatsinks']
    except KeyError as e:
        console.print(f"Config [bold red]Error:[/bold red] Missing key {e} in yaml file.")
        return False

    data_path = find_file(data_name)
    if data_path:
        console.print(f"Found Data at: {data_path}")
        df_original = pd.read_csv(data_path)
    else:
        console.print(f"[bold red]Error:[/bold red] Data file '{data_name}' not found.")
        return False

    # Setup Common Physics
    led_radius = LED_PARAMS['outer_dia_mm'] / 2.0
    target_area_mm2 = math.pi * (led_radius ** 2)
    heat_power_mean = tm.calculate_heat_power(
        LED_PARAMS['forward_voltage_v'], 
        LED_PARAMS['drive_current_a'], 
        LED_PARAMS['heat_coefficient']
    )
    console.print(f"   - Heat Load: {heat_power_mean:.2f} Watts")
    console.print(f"   - Target LED Area: {target_area_mm2:.2f} mm²")
    console.print(f"   - Scenarios to Run: {len(HEATSINK_LIST)}")

    # ==================================================
    # LOOP THROUGH EACH HEATSINKS MODEL
    # ==================================================
    for hs_idx, hs_config in enumerate(HEATSINK_LIST):
        hs_model = hs_config['model']
        r_hs = hs_config['r_heatsink']
        
        console.print("\n" + "-"*60)
        console.print(f"SCENARIO {hs_idx+1}/{len(HEATSINK_LIST)}: {hs_model} (R_th={r_hs} C/W)")
        console.rule(style="dim")
        
        # Calculate system threshold for current heatsink
        system_threshold_cw = tm.calculate_threshold_thermal_resistance(
            LED_PARAMS['max_case_temp_c'], 
            ENV_PARAMS['ambient_temp_c'], 
            heat_power_mean, 
            r_hs
        )
        console.print(f"   - Max Allowable R_tim (Limit): {system_threshold_cw:.4f} C/W")

        # threshold is negative or too low
        if system_threshold_cw <= 0:
            console.print(f"   ERROR: System fails even with ideal TIM (R_tim=0) for {hs_model}. Threshold: {system_threshold_cw:.4f} C/W. Halting pipeline.")
            return False

        results = []
        
        # Monte Carlo Simulation
        for _, row in tqdm(df_original.iterrows(), total=len(df_original), desc=f"Simulating {hs_model}"):
            N = SIM_PARAMS['n_interactions']
            
            # Randomize Inputs
            sim_ambient = np.full(N, ENV_PARAMS['ambient_temp_c'])
            
            # K-Value
            k_base = row['thermal_conductivity_wmk']
            if pd.isna(k_base) or k_base <= 0: k_base = 0.1
            k_unc = UNCERTAINTIES['thermal_conductivity_unc']
            sim_k = np.random.uniform(k_base * (1 - k_unc), k_base * (1 + k_unc), N)
            
            # Thickness
            t_type = str(row['type']).lower()
            if 'grease' in t_type or 'phase change' in t_type:
                 sim_thickness = np.random.uniform(
                     UNCERTAINTIES['grease_blt']['blt_min_mm'], 
                     UNCERTAINTIES['grease_blt']['blt_max_mm'], 
                     N)
            elif 'pad' in t_type:
                 t_base = row['thickness_mm'] if pd.notna(row['thickness_mm']) else 0.5
                 t_unc = UNCERTAINTIES['pad_thickness_unc']
                 sim_thickness = np.random.uniform(t_base * (1 - t_unc), t_base * (1 + t_unc), N)
            else:
                 t_val = row['thickness_mm'] if pd.notna(row['thickness_mm']) else 0.1
                 sim_thickness = np.full(N, t_val)

            # Physics Calculation
            r_tim_sim = tm.calculate_tim_thermal_resistance(sim_thickness, sim_k, target_area_mm2)
            
            # Threshold
            r_threshold_dist = tm.calculate_threshold_thermal_resistance(
                LED_PARAMS['max_case_temp_c'], sim_ambient, heat_power_mean, r_hs
            )
            
            passed = r_tim_sim <= r_threshold_dist
            success_rate = np.sum(passed) / N * 100.0
            
            pass_criteria = 100.0 - SIM_PARAMS['risk_threshold_percent']
            status = "PASS" if success_rate >= pass_criteria else "FAIL"
            
            avg_r_tim = np.mean(r_tim_sim)
            avg_margin = np.mean(r_threshold_dist - r_tim_sim)
            
            t_case_dist = sim_ambient + heat_power_mean * (r_hs + r_tim_sim)
            t_max_99 = np.percentile(t_case_dist, 99)

            results.append({
                'tim_id': row['tim_id'],
                'mpn': row['mpn'],
                'type': row['type'],
                'cost_per_app': row['cost_per_application'],
                'k_wmk': row['thermal_conductivity_wmk'],
                'heatsink_model': hs_model,
                'heatsink_r_th': r_hs,   # Added for Power BI context
                'threshold_limit_cw': system_threshold_cw,
                'calculated_tim_r_cw': avg_r_tim,            
                'reliability_status': status,              
                'pass_probability_pct': success_rate,        
                'avg_margin_cw': avg_margin,
                'max_t_case_99': t_max_99,
                'manufacturer': row['manufacturer'],
                'description': row['description'],
                'thickness_mm': row['thickness_mm']
            })

        # Save Results for THIS Heatsink
        output_dir = os.path.join(PROJECT_ROOT, 'data', 'processed', 'simulation')
        os.makedirs(output_dir, exist_ok=True)
        
        safe_model_name = hs_model.replace(" ", "_").replace(".", "")
        output_file = os.path.join(output_dir, f'simu_results_{safe_model_name}.csv')
        
        res_df = pd.DataFrame(results)
        
        # Reorder columns
        cols_order = [
             'reliability_status', 'pass_probability_pct', 'avg_margin_cw',
             'tim_id', 'mpn', 'type', 'heatsink_model', 'heatsink_r_th',
             'calculated_tim_r_cw', 'threshold_limit_cw', 'max_t_case_99',
             'cost_per_app', 'k_wmk', 'thickness_mm', 'manufacturer', 'description'
        ]
        final_cols = [c for c in cols_order if c in res_df.columns] + [c for c in res_df.columns if c not in cols_order]
        res_df = res_df[final_cols]
        
        precision = {
            'threshold_limit_cw': 4, 
            'calculated_tim_r_cw': 4, 
            'pass_probability_pct': 2,
            'avg_margin_cw': 4, 
            'max_t_case_99': 2   
        }
        res_df = res_df.round(precision)
        
        res_df.to_csv(output_file, index=False)
        console.print(f"Results saved to: {output_file}")
        
        # Quick Summary
        passed_count = len(res_df[res_df['reliability_status'] == 'PASS'])
        console.print(f"Summary for {hs_model}: {passed_count}/{len(res_df)} items passed.")
        
    return True

if __name__ == "__main__":
    run_simulation()