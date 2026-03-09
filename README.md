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
- **Machine Learning Recommendations**: Uses K-Means Clustering to categorize TIMs into groups like "Best Value", "Standard", or "Avoid".

---

## 📂 Directory Structure

- **`script/`**: Core executable scripts.
  - `run_pipeline.py`: Main orchestration script to run the full pipeline automation.
  - `data_processing.py`: Cleans raw data and calculates unit costs.
  - `simulation.py`: Runs the Monte Carlo simulation for defined heatsink scenarios.
  - `ml_analysis.py`: Analyzes simulation results and generates final recommendations.
  - `thermal_model.py`: Library for thermal calculations (Power, R_th).
  - `utils.py`: Helper functions.
- **`data/`**:
  - `processed/`:
    - `cleanned_data.csv`: Cleaned TIM dataset.
    - `cost_data.csv`: TIM data with calculated cost per application.
    - `recommendations.db`: SQLite database storing simulation results and scenarios.
- **`config/`**:
  - `simulation_config.yaml`: Configuration for simulation parameters (LED specs, Heatsink models, Uncertainties).
- **`notebooks/`**: Jupyter notebooks for exploratory data analysis (EDA) and prototyping.

---

## Usage

### 1. Prerequisites
Install the required Python packages:
```bash
pip install -r requirements.txt
```

### 2. Configure Simulation
Edit `config/simulation_config.yaml` to adjust:
- **LED Parameters**: `drive_current_a`, `forward_voltage_v`, `max_case_temp_c`.
- **Environment**: `ambient_temp_c`.
- **Heatsinks**: List of heatsink models and their thermal resistance (`r_heatsink`).
- **Uncertainties**: Manufacturing tolerances (e.g., `thermal_conductivity_unc`, `grease_blt`).

### 3. Run Pipeline
Execute the full automated pipeline to process data, run predictions, and save results to the database.
```bash
python script/run_pipeline.py --scenario "My Run Scenario"
```
*Output: `data/processed/recommendations.db`, `data/processed/simulation/simu_results_*.csv`*

```bash
```

---

## 📊 Output Explanation

The final outputs in the database (`recommendations.db`) and CSV records are optimized for visualization and contain:

### 🏷️ Recommendation
- **`recommendation_group`**:
  - 🏆 **Best Value**: High performance, reasonable cost.
  - ✅ **Standard**: Good balance for general use.
  - 🏭 **Industrial**: High performance, higher cost (for demanding applications).
  - ❌ **Avoid**: High risk of failure or poor cost-benefit.

### ⚙️ Identity & Specs
- **`tim_id`**, **`mpn`**, **`manufacturer`**: TIM Identifiers.
- **`description`**: Product description.
- **`type`**: Material type (Grease, Pad, etc.).

### 💰 Cost & Performance
- **`cost_per_app`**: Estimated cost per 1 LED application (THB).
- **`calculated_tim_r_cw`**: Effective Thermal Resistance of the TIM (C/W).
- **`pass_probability_pct`**: % chance the TIM keeps the LED under the max temperature.
- **`reliability_status`**: **PASS** / **FAIL** based on the simulation threshold.
- **`avg_margin_cw`**: Thermal margin remaining (Safety factor).

### 🌡️ Environment Context
- **`heatsink_model`**: Name of the heatsink used in simulation.
- **`heatsink_r_th`**: Thermal Resistance of the heatsink (C/W).

---

## ✅ Project Progress / Goals

### 1. Data Pipeline & Processing
- [x] **Data Collection**: Gather raw TIM datasheets and prices.
- [x] **Data Cleaning**: Handle missing values, mixed units, and formatting issues (`data_processing.py`).
- [x] **Cost Calculation**: Implement logic for cost per application (Volume/Area based).

### 2. Physical Modeling & Simulation
- [x] **Thermal Model**: Develop `thermal_model.py` to calculate R_th and Heat Load.
- [x] **Monte Carlo Simulation**: Create randomized simulation loop accounting for BLT and K uncertainty.
- [x] **Scenario Testing**: Support multiple heatsink models in one run (`simulation_config.yaml`).

### 3. Analysis
- [x] **Pass/Fail Logic**: Establish reliability thresholds based on max LED temperature.
- [x] **K-Means Clustering**: Group TIMs by Performance vs. Cost (`ml_analysis.py`).
- [x] **Database Integration**: Implemented SQLite to store run history and compare simulation scenarios.

### 4. Future Work / To-Do
- [ ] **Publish Dashboard**: Deploy Power BI Dashboard for team access.
- [ ] **More Heatsinks**: Expand the library of heatsink models.
- [ ] **Dynamic Pricing**: Connect to live API for real-time pricing.