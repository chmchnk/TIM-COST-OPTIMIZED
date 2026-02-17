# Cost and Uncertainty of Thermal Interface Materials Analysis

This project analyzes the cost-effectiveness and reliability of Thermal Interface Materials (TIMs) for LED applications using Monte Carlo simulations and Machine Learning.

## 🎯 Project Overview

The goal is to recommend the optimal TIM by balancing **thermal performance** (Thermal Resistance) and **cost**, while accounting for real-world uncertainties such as:
- Variations in Bond Line Thickness (BLT) during application.
- Deviations in Thermal Conductivity from datasheet specs.
- Environmental factors (Ambient Temperature).

### Key Features
- **Physics-Based Thermal Model**: Calculates LED heat load and total system thermal resistance.
- **Monte Carlo Simulation**: Simulates thousands of scenarios to estimate the probability of thermal failure (Pass/Fail).
- **Machine Learning Recommendations**: Uses K-Means Clustering to categorize TIMs into groups like "Best Value", "Premium", or "Avoid".

---

## 📂 Directory Structure

- **`script/`**: Core executable scripts.
  - `simulation.py`: Runs the Monte Carlo simulation.
  - `ml_analysis.py`: Analyzes simulation results and generates recommendations.
  - `thermal_model.py`: Library for thermal calculations.
  - `data_processing.py`: Utilities for data cleaning.
- **`data/`**:
  - `processed/cost_data.csv`: Main input dataset (TIM specs & prices).
  - `processed/simu_results_*.csv`: Output from simulations.
  - `processed/final_recommendation_data.csv`: Final output from ML analysis.
- **`config/`**:
  - `simulation_config.yaml`: Configuration for simulation parameters (LED specs, Heatsink models, Uncertainties).
- **`notebooks/`**: Jupyter notebooks for exploratory data analysis (EDA) and prototyping.

---

## 🚀 Usage

### 1. Prerequisites
Install the required Python packages:
```bash
pip install pandas numpy scikit-learn pyyaml tqdm
```

### 2. Configure Simulation
Edit `config/simulation_config.yaml` to adjust:
- **LED Parameters**: `drive_current_a`, `forward_voltage_v`, `max_case_temp_c`.
- **Environment**: `ambient_temp_c`.
- **Heatsinks**: List of heatsink models and their thermal resistance (`r_heatsink`).
- **Uncertainties**: Manufacturing tolerances (e.g., `thermal_conductivity_unc`, `grease_blt`).

### 3. Run Simulation
Execute the simulation script to generate pass/fail probabilities for each TIM across defined heatsink scenarios.
```bash
python script/simulation.py
```
*Output: `data/processed/simu_results_*.csv`*

### 4. Run Analysis & Recommendations
Run the ML analysis script to cluster TIMs and identify the best options.
```bash
python script/ml_analysis.py
```
*Output: `data/processed/final_recommendation_data.csv`*

---

## 📊 Output Explaination

The final output (`final_recommendation_data.csv`) contains:
- **`tim_id`**, **`mpn`**: TIM Identifiers.
- **`pass_probability_pct`**: % chance the TIM keeps the LED under the max temperature.
- **`reliability_status`**: PASS/FAIL based on risk threshold.
- **`recommendation_group`**:
  - 🏆 **Best Value**: High performance, reasonable cost.
  - 💰 **Standard / Mid-Range**: Average performance and cost.
  - 💎 **Premium / Industrial**: High cost, very high performance.
  - ❌ **Avoid / Low Performance**: Does not meet requirements or poor cost-benefit.