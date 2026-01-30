# src/utils.py
import yaml

def load_config(config_path='config/simulation_config.yaml'):
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
    return config