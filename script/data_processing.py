import pandas as pd
import numpy as np
import glob
import os
import re
import yaml
import math

# ------------------------------------------------------
# READ RAW DATA AND MERGE THEM INTO DESIRED FOLDER
# ------------------------------------------------------
def merge_data(df):
    current_dir = os.getcwd()   # Find current directory
    # Parent directory
    project_root = os.path.abspath(os.path.join(current_dir, '..'))
    if not os.path.exists(os.path.join(project_root, 'data')):
        project_root = current_dir

    # Define paths
    raw_path = os.path.join(project_root, 'data', 'raw')
    processed_path = os.path.join(project_root, 'data', 'processed')
    output_filename = 'merged_data.csv'

    # Read all files and merge
    print(f"Reading from: {raw_path}")
    print(f"Saving to:    {processed_path}")

    all_files = glob.glob(os.path.join(raw_path, "*.csv"))

    if all_files:
        li = []
        for filename in all_files:
            df = pd.read_csv(filename, index_col=None, header=0)
            df['source_file'] = os.path.basename(filename) 
            li.append(df)

        frame = pd.concat(li, axis=0, ignore_index=True)

        os.makedirs(processed_path, exist_ok=True)  # Create destination folder if doesn't exist
        
        save_path = os.path.join(processed_path, output_filename)
        frame.to_csv(save_path, index=False)

        print(f"\nSaved to:\n{save_path}")
    else:
        print(f"There are no CSV files in the folder {raw_path}")

# ------------------------------------------------------
# CLEANING MERGED DATA
# ------------------------------------------------------
def clean_raw_data(df):
    df = pd.read_csv("data/processed/merged_data.csv")
    columns_to_drop = ["Category", "source_file"]   # Drop unneeded columns
    df.drop(columns=columns_to_drop, inplace=True) 

    # Insert blank new columns and create new dictinary for new columns 
    id_columns = {
        "tim_id":""
    }
    weight_columns = {
        "weight_g":""
    }
    for col, default_value in id_columns.items():
        df.insert(loc=0, column=col, value=default_value)
    for col, default_value in weight_columns.items():
        df.insert(loc=len(df.columns), column=col, value=default_value)

    rename_profile = {
        "MPN":"mpn",
        "Manufacturer":"manufacturer",
        "Description":"description",
        "Thermal_Conductivity":"thermal_conductivity_wmk",
        "Thickness":"thickness_mm",
        "Width":"width_mm",
        "Length":"length_mm",
        "Price_THB":"price_thb"
    }
    df.rename(columns=rename_profile, inplace=True)
    df = df[df["thermal_conductivity_wmk"] != "-"].copy()
    df = df[df["thickness_mm"] != "-"].copy()
    df = df[df["price_thb"] != "Active"].copy()
    df["thermal_conductivity_wmk"] = df["thermal_conductivity_wmk"].str.replace("W/m-K", "", regex=False).str.strip()

    # CREATE TIM TYPE BASE ON KEYWORD IN DESCRIPTION
    def define_nontim(type_str):
        if pd.isna(type_str):
            return False
        t = str(type_str).lower()
        nontim_keyword = [
            "heat sink", "fan", "filter", "circuit breaker", "heatsink", "extrusion",
            "amplifier", "sensor", "controller", "voltage", "channel", "insulator",
            "Gasket", "Kit"
        ]
        tim_keyword = [
            "gel", "putty", "grease", "liquid", "compound", " gap filler", "adhesive", 
            "epoxy", "potting", "hardener", "pad", "paste"
        ]
        if any(nt in t for nt in nontim_keyword):
            if not any(tk in t for tk in tim_keyword):
                return True
        return False
    def define_timtype(type_str):
        desc = type_str
        t = str(type_str).lower()
        # Other (Permanant bond)
        if "tape" in t: 
            return "Other"
        if any(x in t for x in ["epoxy", "potting", "glue", "hardener", "cement", "bond"]):
            return "Other"
        if "adhesive" in t and "pad" not in t:
            return "Other"
        # PCM -> Grease / Thermal Pad
        if "phase change" in t or "pcm" in t:
            liquid_keywords = ["paste", "compound", "syringe", "tube", "can", "jar", "grease", "dispensable", "flow"]
            if any(x in t for x in liquid_keywords):
                return "Grease"
            return "Thermal Pad"
        # Grease
        grease_keywords = [
            "grease", "paste", "gel", "putty", "liquid", "compound", 
            "fluid", "cartridge", "syringe", "tube", "dispensable"
        ]
        if any(x in t for x in grease_keywords):
            return "Grease"
        # Thermal Pad
        pad_keywords = ["pad", "sheet", "gap pad", "thermal pad", "tflex","tpli"]
        if any(x in t for x in pad_keywords):
            return "Thermal Pad"
        return "Other"

    is_unneed = df["description"].apply(define_nontim)
    df = df[~is_unneed].copy()
    df["type"] = df["description"].apply(define_timtype)
    df["type"] = df["type"].fillna("Other") 

    df.sort_values(by=["type","price_thb"], inplace=True)   # sort data from cheapest to most expensive in each category

    # CREATE TIM ID FOR EACH TYPE
    def generate_id(df):
        # dictionary to track counts for each category
        count_profile = {
            "Thermal Pad": 0,
            "Grease": 0,
            "Other": 0
        }
        ids = []
        for cat in df["type"]:
            if pd.isna(cat) or cat not in count_profile:
                target_cat = "Other"
            else:
                target_cat = cat
            count_profile[target_cat] += 1
            num = count_profile[target_cat]

            # Given prefix
            if cat == "Thermal Pad":
                prefix = "TP"
            elif cat == "Grease":
                prefix = "GR"
            else:
                prefix = "OT"
        
            tim_id = f"{prefix}-{num:04d}"  # ID with leading zeros
            ids.append(tim_id)
        return ids
    df["tim_id"] = generate_id(df)

    # EXTRACT DIMENSION VALUE FOR WIDTH_MM AND LENGTH_MM COLUMNS
    def extract_dim_mm(val):
        if pd.isna(val): return None
        s = str(val).lower().strip()
        
        for pat in [r'\(\s*([\d\.]+)\s*mm\s*\)', r'([\d\.]+)\s*mm']:    # For example, (xx mm) or xx mm
            m = re.search(pat, s)
            if m: return float(m.group(1))
        
        # For inch pattern 
        if '"' in s and 'mm' not in s:
            m = re.search(r'([\d\.]+)\s*"', s)
            if m: return float(m.group(1)) * 25.4
            
        try: return float(s)
        except: return None

    # EXTRACT DIMENSION VALUE FOR WIDTH_MM AND LENGTH_MM FROM DESCRIPTION
    def parse_desc(desc):
        if pd.isna(desc): return None, None
        s = str(desc).lower()
        
        # For example, 5x5mm
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:mm)?\s*[xX]\s*(\d+(?:\.\d+)?)\s*mm', s)
        if m: return float(m.group(1)), float(m.group(2))
        
        # For inch pattern
        m = re.search(r'(\d+(?:\.\d+)?)\s*"?\s*[xX]\s*(\d+(?:\.\d+)?)\s*"', s)
        if m: return float(m.group(1))*25.4, float(m.group(2))*25.4
        
        # For mixed inch and mm pattern
        m = re.search(r'(\d+(?:\.\d+)?)\s*"\s*[xX]\s*(\d+(?:\.\d+)?)', s)
        if m:
            v1 = float(m.group(1)) * 25.4
            v2_str = m.group(2)
            # Checking unit
            if re.search(re.escape(v2_str) + r'\s*m\b', s): return v1, float(v2_str) * 1000 # meter
            if re.search(re.escape(v2_str) + r'\s*mm', s): return v1, float(v2_str)        # millimeter
            return v1, float(v2_str) * 25.4 
            
        return None, None

    def process_row(row):
        # Extract from initial column first
        w = extract_dim_mm(row['width_mm'])
        l = extract_dim_mm(row['length_mm'])
        
        # For missing value, extract from description
        if w is None or l is None:
            dw, dl = parse_desc(row['description'])
            if dw is not None and dl is not None:
                if w is None: w = dw
                if l is None: l = dl
                
        return w, l

    mask_tp = df['type'].isin(['Thermal Pad'])
    res = df.loc[mask_tp].apply(process_row, axis=1, result_type='expand')   

    if not res.empty:
        df.loc[mask_tp, 'width_mm'] = res[0]
        df.loc[mask_tp, 'length_mm'] = res[1]

    # Remove width_mm and length_mm value from other types
    mask_other = ~df['type'].isin(['Thermal Pad'])
    df.loc[mask_other, ['width_mm', 'length_mm']] = np.nan

    # Remove row with missing width and length values
    mask_keep = (~mask_tp) | (mask_tp & df['width_mm'].notna() & df['length_mm'].notna())
    df = df[mask_keep]

    # EXTRACT THICKNESS_MM VALUE
    def extract_thck_mm(val):
        if pd.isna(val): return None
        s = str(val).lower().strip()
        
        if re.search(r'\d\s*[xX*]\s*\d', s):
            return None

        m = re.search(r'(\d*\.?\d+)\s*(mm|mil|in|")', s)
        if m:
            v = float(m.group(1))
            unit = m.group(2)
            if unit == 'mil': return v * 0.0254
            if unit == 'in' or unit == '"': return v * 25.4
            return v
        
        try:
            return float(s)
        except:
            return None
            
    def extract_thck_from_desc(desc):
        if pd.isna(desc): return None
        s = str(desc).lower()
        
        m = re.search(r'(?<![\dxX]\s)(\d*\.?\d+)\s*(mm|mil|in|")\s*(?:thk|thick)', s)
        if m:
            v = float(m.group(1))
            unit = m.group(2)
            if unit == 'mil': return v * 0.0254
            if unit == 'in' or unit == '"': return v * 25.4
            return v
            
        m = re.search(r'(?:thk|thick)[^0-9]*(\d*\.?\d+)\s*(mm|mil|in|")', s)
        if m:
            v = float(m.group(1))
            unit = m.group(2)
            if unit == 'mil': return v * 0.0254
            if unit == 'in' or unit == '"': return v * 25.4
            return v
            
        return None

    df['thickness_clean'] = df['thickness_mm'].apply(extract_thck_mm)
    mask_nan = df['thickness_clean'].isna()
    df.loc[mask_nan, 'thickness_clean'] = df.loc[mask_nan, 'description'].apply(extract_thck_from_desc)
    df['thickness_mm'] = df['thickness_clean']
    df.drop(columns=['thickness_clean'], inplace=True)

    # Remove thickness value from other types
    mask_target = df['type'].isin(['Thermal Pad'])
    df.loc[~mask_target, ['thickness_mm']] = np.nan     # Thickness in Other and Grease type will be NaN
    # Remove row with missing thickness values of thermal pad and pcm
    mask_keep = (~mask_target) | (mask_target & df['thickness_mm'].notna())
    df = df[mask_keep]

    def extract_weight(desc):
        if pd.isna(desc): return None
        desc = str(desc).lower()
        
        # Extract gram unit 
        match_g = re.search(r'(\d*\.?\d+)\s*(gram|g|oz|ounce|ml|cc|kg|mg|lb)', desc)
        if match_g:
            val = float(match_g.group(1))
            unit = match_g.group(2)
    
            # need to clarify that there is no density information available for accurate conversion
            # convert units
            if unit in ['g', 'gram']: return val
            if unit in ['oz', 'ounce']: return val * 28.35  # ounces -> grams
            if unit == 'lb': return val * 453.6  # pounds -> grams
            if unit == 'kg': return val * 1000   # kilograms -> grams
            if unit == 'mg': return val / 1000   # milligrams -> grams
            if unit in ['ml','cc']: return val * 2.5 # volume -> grams (assumed Density ~2.5)
        
        return None

    df["weight_g"] = df["description"].apply(extract_weight)

    # Remove weight value from Thermal pad and PCM
    mask_target = df['type'].isin(['Other', 'Grease'])
    df.loc[~mask_target, ['weight_g']] = np.nan     # weight in Thermal Pad and PCM type will be NaN

    # Remove row with missing weight values of grease and other
    mask_keep = (~mask_target) | (mask_target & df['weight_g'].notna())
    df = df[mask_keep]

    # Manage str into numeric
    def clean_numeric(x):
        if pd.isna(x):
            return x
        if isinstance(x, str):
            x = x.split(',')[0]     # For example: 20, 56 will should 20 as the choosen value
            import re
            x = re.sub(r'[^0-9.]', '', x)
        return x

    target_column = ['thermal_conductivity_wmk', 'thickness_mm', 'length_mm', 'width_mm',
                    'price_thb', 'weight_g'   
                    ]

    df[target_column] = df[target_column].map(clean_numeric)   # Apply for each element

    for col in target_column:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    precision = {'thermal_conductivity_wmk':2, 
                'thickness_mm':2, 
                'length_mm':2, 
                'width_mm':2,
            
                'price_thb':2, 
                'weight_g':1   
    }

    df = df.round(precision)

    # drop rows with NaN value in thermal_conductivity_wmk ccolumns
    df = df.dropna(subset=['thermal_conductivity_wmk'])
    df.to_csv("cleanned_data.csv", index=False)
    type_counts = df["type"].value_counts()
    print(type_counts)

    return df

# -----------------------------------------------------
# LOAD CONFIG FROM SIMULATION_CONFIG.YAML
# -----------------------------------------------------
def load_config(config_path):
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)


# -----------------------------------------------------
# COST CALCULATION (PRICE/UNIT, COST/APPLICATION)
# -----------------------------------------------------
def feature_calculation(df, config):
    df['area_mm2'] = np.nan
    df['area_mm2'] = (df['length_mm'] * df['width_mm'])

    # PRICE/UNIT
    df["price_per_mm2"] = np.nan
    mask_pad = df['type'].isin(['Thermal Pad'])
    df.loc[mask_pad, 'price_per_mm2'] = (df.loc[mask_pad, 'price_thb'] / df.loc[mask_pad, 'area_mm2']) 

    df["price_per_gram"] = np.nan
    mask_pad = df['type'].isin(['Grease','Other'])
    df.loc[mask_pad, 'price_per_gram'] = (df.loc[mask_pad, 'price_thb'] / df.loc[mask_pad, 'weight_g']) 

    # PRICE/APPLICATION
    led_diameter_mm = config['heat_source']['outer_dia_mm']
    target_area_mm2 = math.pi * ((led_diameter_mm/2) ** 2)
    blt_average_mm = (config['uncertainties']['grease_blt']['blt_max_mm'] + config['uncertainties']['grease_blt']['blt_min_mm'])/2
    grease_density = config['constants']['grease_density']

    # grease application weight
    # aplication_volumn_cc = (target_area_mm2 * blt_average_mm)/1000 -> change unit into gram
    application_volumn_cc = (target_area_mm2 * blt_average_mm)/1000
    application_weight_g = application_volumn_cc * grease_density

    mask_pad = df['type'].isin(['Thermal Pad'])
    df.loc[mask_pad, 'cost_per_application'] = ((df.loc[mask_pad, 'price_per_mm2']) * target_area_mm2)

    mask_grease = df['type'].isin(['Grease','Other'])
    df.loc[mask_grease, 'cost_per_application'] = ((df.loc[mask_grease, 'price_per_gram']) * application_weight_g)

    target_column = ['area_mm2', 'price_per_mm2', 'price_per_gram', 'cost_per_application']
    precision = {'area_mm2':2, 
                'price_per_mm2':4, 
                'price_per_gram':2, 
                'cost_per_application':2,
    }

    df = df.round(precision)
    return df

if __name__ == "__main__":
    merge_data(None)
    clean_df = clean_raw_data(None)
    config_path = "config/simulation_config.yaml"
    if os.path.exists(config_path):
        config = load_config(config_path)
        cost_df = feature_calculation(clean_df, config)
        cost_df.to_csv("cost_data.csv", index=False)
    else:
        print(f"Can't find config file at {config_path}")