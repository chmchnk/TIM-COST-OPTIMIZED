import numpy as np
import pandas as pd

# -----------------------------------------------------
# POWER AND HEATLAOD CALCULATION
# -----------------------------------------------------
def calculate_heat_power(forward_voltage_v, drive_current_a, heat_coefficient):

    # Calculate Heat Load from electrical datasheet
    # Formula: Heat Power = (V * I) * Heat_Coefficient
    
    # Note: Since LED change electrical energy into light and heat  
    #       Heat Coefficient is the range of waste heat produced as a percentage of the input power to the
    #         module is ~ 75% for Warm White (Considering for worst case)
    
    # Parameters:
    #     forward_voltage_v: 
    #     drive_current_a: Max drive current
    #     heat_coefficient:
        
    # Returns:
    #     heat_power: (Unit: Watt)

    electrical_power = forward_voltage_v * drive_current_a
    heat_power_watt = electrical_power * heat_coefficient
    return heat_power_watt

# -----------------------------------------------------
# TIM THERMAL RESISTANCE CALCULATION (C/W)
# -----------------------------------------------------
def calculate_tim_thermal_resistance(thickness_mm, thermal_conductivity_wmk, area_mm2):

    # Calculate Thermal Resistance of TIM (tim_thermal_resistance)
    # Formula: R = L / (k * A)
    
    # CHANGING UNIT TO M AND M^2
    thickness_m = thickness_mm / 1000.0 
    area_m2 = area_mm2 / 1_000_000.0
    
    with np.errstate(divide='ignore', invalid='ignore'):
        tim_thermal_resistance_cw = thickness_m / (thermal_conductivity_wmk * area_m2)
    
    return tim_thermal_resistance_cw

# -----------------------------------------------------
# THRESHOLD THERMAL RESISTANCE CALCULATION (C/W)
# -----------------------------------------------------
def calculate_threshold_thermal_resistance(max_case_temp_c, ambient_temp_c, heat_power, heatsink_thermal_resistance):

    # Allowable thermal resistance of the system
    # Using T_case with max_temp_c for maximum operating parameter
    # Calculate heatsink temperature first, with the reference point from heatsink -> ambient
    heatsink_temp_c = ambient_temp_c + (heatsink_thermal_resistance * heat_power)
    threshold_thermal_resistance_tim_cw = (max_case_temp_c - heatsink_temp_c) / heat_power
    
    return threshold_thermal_resistance_tim_cw