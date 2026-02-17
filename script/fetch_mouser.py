import os
import requests
import pandas as pd
import time
import re
from dotenv import load_dotenv

# -----------------------------------------------------
# CONFIGURATIONS
# -----------------------------------------------------
load_dotenv()
MOUSER_API_KEY = os.getenv('MOUSER_API_KEY')
MOUSER_ENDPOINT = "https://api.mouser.com/api/v1/search/keyword"

# Target Columns
TARGET_COLUMNS = [
    "MPN", 
    "Manufacturer", 
    "Category", 
    "Description", 
    "Thermal_Conductivity", 
    "Thickness", 
    "Width", 
    "Length", 
    "Price_THB"
]

# -----------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------
def clean_price(price_str):
    """Cleans price string and converts to float."""
    if not price_str: return None
    clean = re.sub(r'[^\d.]', '', str(price_str))
    try:
        return float(clean)
    except ValueError:
        return None

def parse_attributes(attributes_list):
    """Parses product attributes from API response."""
    specs = {'k': None, 't': None, 'w': None, 'l': None}
    if not attributes_list: return specs

    for attr in attributes_list:
        name = attr.get('AttributeName', '').lower()
        val = attr.get('AttributeValue', '')

        if 'thermal conductivity' in name:
            specs['k'] = val
        elif 'thickness' in name or 'height' in name:
            specs['t'] = val
        elif 'width' in name:
            specs['w'] = val
        elif 'length' in name:
            specs['l'] = val
            
    return specs

def extract_from_desc_fallback(desc):
    """Fallback method to extract specs from description using Regex."""
    data = {'t': None, 'w': None, 'l': None, 'k': None}
    if not desc: return data
    desc = desc.lower()

    m_thick = re.search(r'(?:thickness\s*)?(\d+(?:\.\d+)?)\s*mm', desc)
    if m_thick: data['t'] = f"{m_thick.group(1)} mm"
    
    m_dim = re.search(r'(\d+(?:\.\d+)?)\s*[x*]\s*(\d+(?:\.\d+)?)', desc)
    if m_dim: 
        data['w'] = f"{m_dim.group(1)} mm"
        data['l'] = f"{m_dim.group(2)} mm"
        
    m_k = re.search(r'(\d+(?:\.\d+)?)\s*(?:w\/m|w\/mk)', desc)
    if m_k: data['k'] = f"{m_k.group(1)} W/m-K"

    return data

# -----------------------------------------------------
# MAIN FETCHING LOGIC
# -----------------------------------------------------
def fetch_mouser_data():
    if not MOUSER_API_KEY:
        raise ValueError("Error: MOUSER_API_KEY missing in .env")

    keywords = [
        "Thermal Grease", "Thermal Paste", "Thermal Pad", 
        "Thermal Gap Pad", "Phase Change Material"
    ]
    
    all_rows = []
    
    print("--- Starting Mouser API Extraction ---")
    
    for kw in keywords:
        print(f"Querying: {kw}...")
        
        start_rec = 0
        limit_per_req = 50
        total_found = 1 
        
        while start_rec < total_found:
            # Body: Search payload
            body = {
                "SearchByKeywordRequest": {
                    "keyword": kw,
                    "records": limit_per_req,
                    "startingRecord": start_rec,
                    "searchOptions": "None",
                    "searchWithYourSignUpLanguage": "Thailand"
                }
            }
            
            # Headers: Content-Type JSON
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            # *** Critical Fix: apiKey must be sent via params, not just headers ***
            params = {
                "apiKey": MOUSER_API_KEY
            }

            try:
                # Send params=params to requests.post
                resp = requests.post(MOUSER_ENDPOINT, params=params, json=body, headers=headers)
                
                if resp.status_code != 200:
                    print(f"  [Error] API Status {resp.status_code}: {resp.text}")
                    break
                
                data_json = resp.json()
                
                # Check for Mouser API errors
                if data_json.get('Errors'):
                     print(f"  [Mouser Error]: {data_json.get('Errors')}")
                     break

                search_results = data_json.get('SearchResults', {})
                parts = search_results.get('Parts', [])
                total_found = search_results.get('NumberOfResult', 0)
                
                if not parts:
                    break

                for p in parts:
                    mpn = p.get('ManufacturerPartNumber')
                    mfr = p.get('Manufacturer')
                    desc = p.get('Description')
                    category = p.get('Category')
                    
                    attrs = p.get('Attributes', [])
                    spec_vals = parse_attributes(attrs)
                    
                    if not spec_vals['t'] or not spec_vals['k']:
                        fallback = extract_from_desc_fallback(desc)
                        spec_vals['t'] = spec_vals['t'] or fallback['t']
                        spec_vals['k'] = spec_vals['k'] or fallback['k']
                        spec_vals['w'] = spec_vals['w'] or fallback['w']
                        spec_vals['l'] = spec_vals['l'] or fallback['l']

                    price_thb = None
                    
                    for pb in p.get('PriceBreaks', []):
                        currency = pb.get('Currency', 'USD')
                        qty = pb.get('Quantity', 999)
                        price_str = pb.get('Price', '')
                        
                        is_thb = (currency == 'THB') or ('฿' in price_str)
                        
                        if is_thb and qty <= 10: 
                            val = clean_price(price_str)
                            if val:
                                price_thb = val
                                break 

                    if price_thb:
                        all_rows.append({
                            "MPN": mpn,
                            "Manufacturer": mfr,
                            "Category": category,
                            "Description": desc,
                            "Thermal_Conductivity": spec_vals['k'],
                            "Thickness": spec_vals['t'],
                            "Width": spec_vals['w'],
                            "Length": spec_vals['l'],
                            "Price_THB": price_thb
                        })

                start_rec += limit_per_req
                print(f"  Processed {start_rec}/{total_found}...")
                
                time.sleep(1)

            except Exception as e:
                print(f"  [Exception] {e}")
                break
                
    return pd.DataFrame(all_rows)

# -----------------------------------------------------
# EXECUTION
# -----------------------------------------------------
if __name__ == "__main__":
    df = fetch_mouser_data()
    
    if not df.empty:
        df = df[TARGET_COLUMNS]
        df = df.drop_duplicates(subset=['MPN'])
        
        # Ensure data/raw directory exists
        output_dir = os.path.join(os.getcwd(), 'data', 'raw')
        os.makedirs(output_dir, exist_ok=True)
        
        filename = os.path.join(output_dir, "mouser_tim_data.csv")
        df.to_csv(filename, index=False)
        print(f"\nSuccess! Saved {len(df)} items to {filename}")
        try:
            print(df[['MPN', 'Thickness', 'Price_THB']].head().to_markdown(index=False))
        except:
            print(df[['MPN', 'Thickness', 'Price_THB']].head())
    else:
        print("No data found.")