import pandas as pd
import glob
import os
import re

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
        # Phase Change Material
        if "phase change" in t or "pcm" in t:
            return "Phase Change Material"
        # Other (Permanent bond)
        if "tape" in t: 
            return "Other" 
        if "epoxy" in t or "potting" in t or "glue" in t or "hardener" in t:
            return "Other"
        if "adhesive" in t and "pad" not in t:
            return "Other"
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
            "Phase Change Material": 0,
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
            elif cat == "Phase Change Material":
                prefix = "PCM"
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

    mask_tp = df['type'].isin(['Thermal Pad', 'Phase Change Material'])
    res = df.loc[mask_tp].apply(process_row, axis=1, result_type='expand')   

    if not res.empty:
        df.loc[mask_tp, 'width_mm'] = res[0]
        df.loc[mask_tp, 'length_mm'] = res[1]

    # Remove width_mm and length_mm value from other types
    mask_other = ~df['type'].isin(['Thermal Pad', 'Phase Change Material'])
    df.loc[mask_other, ['width_mm', 'length_mm']] = np.nan

    # Remove row with missing width and length values
    mask_keep = (~mask_tp) | (mask_tp & df['width_mm'].notna() & df['length_mm'].notna())
    df = df[mask_keep]

    # EXTRACT THICKNESS_MM VALUE
    def extract_thck_mm(val):
        if pd.isna(val): return None
        s = str(val).lower().strip()
        
        # Extract value in thickness_mm column
        pattern_match = re.findall(r'\((.*?)\)', s)
        for value in pattern_match: 
            m = re.search(r'(\d*\.?\d+)\s*(mm|")', value)
            if m: 
                val = float(m.group(1))
                unit = m.group(2)
                return val*25.4 if unit == '"' else val
            
        # Extract from description
        pattern = [
            r'(\d*\.?\d+)\s*(mm|")\s*Thickness',    # For example, 0.005" Thickness
            r'Thickness,\s*(\d*\.?\d+)\s*(mm|")',   # For example, Thickness, 0.5 mm
            r'(\d*\.?\d+)\s*mm',                # For example, 1.5mm
            r'(\d*\.?\d+)"'                     # For example, 0.02"
        ]

        for pat in pattern:
            m = re.search(pat, s, re.I)
            if m:
                val = float(m.group(1))
                try:
                    unit = m.group(2)
                except IndexError:
                    unit = '"' if '"' in pat else 'mm'
                return val*25.4 if unit == '"' else val
        return None

    df["thickness_mm"] = df["description"].apply(extract_thck_mm)

    # Remove thickness value from other types
    mask_target = df['type'].isin(['Thermal Pad', 'Phase Change Material'])
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

    df[target_column] = df[target_column].applymap(clean_numeric)   # Apply for each element

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
