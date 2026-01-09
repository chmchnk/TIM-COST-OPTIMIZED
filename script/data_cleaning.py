import pandas as pd
import glob
import os
import re

## Merge all CSV files in data/raw/ into a single CSV in data/processed/
# Find current directory
current_dir = os.getcwd()

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

    # สร้าง folder ปลายทางถ้ายังไม่มี
    os.makedirs(processed_path, exist_ok=True)
    
    save_path = os.path.join(processed_path, output_filename)
    frame.to_csv(save_path, index=False)

    print(f"\nSaved to:\n{save_path}")
else:
    print(f"There are no CSV files in the folder {raw_path}")

## Data Cleaning
df = pd.read_csv("data/processed/merged_data.csv")
# Drop unneeded columns
columns_to_drop = ["Category", "source_file"]
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

# rename columns
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

# Create TIM type
def define_nontim(type_str):
    if pd.isna(type_str):
        return False
    
    t = str(type_str).lower()
    nontim_keyword = [
        "heat sink", "fan", "filter", "circuit breaker", "heatsink", "extrusion",
        "amplifier", "sensor", "controller", "voltage", "channel"
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

    # Thermal Paste
    grease_keywords = [
        "grease", "paste", "gel", "putty", "liquid", "compound", 
        "fluid", "cartridge", "syringe", "tube", "dispensable"
    ]
    if any(x in t for x in grease_keywords):
        return "Thermal Paste"

   # Thermal Pad
    pad_keywords = [
        "pad", "sheet", "gap pad", "thermal pad", "tflex","tpli"
    ]
    if any(x in t for x in pad_keywords):
        return "Thermal Pad"
    return "Other"
# Apply function and count values in category column
is_unneed = df["description"].apply(define_nontim)
df = df[~is_unneed].copy()
df["type"] = df["description"].apply(define_timtype)
# Display the updated DataFrame with the new "category"
print(df)



