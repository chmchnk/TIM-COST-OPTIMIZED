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
DIGIKEY_CLIENT_ID = os.getenv('DIGIKEY_CLIENT_ID')
DIGIKEY_CLIENT_SECRET = os.getenv('DIGIKEY_CLIENT_SECRET')

DK_TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
DK_SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"

TARGET_COLUMNS = [
    "MPN", "Manufacturer", "Category", "Description", 
    "Thermal_Conductivity", "Thickness", "Width", "Length", "Price_THB"
]

# -----------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------
def get_digikey_token():
    """Authenticates with DigiKey API to retrieve access token."""
    if not DIGIKEY_CLIENT_ID or not DIGIKEY_CLIENT_SECRET:
        raise ValueError("Error: DigiKey ID/Secret missing in .env")
    data = {"client_id": DIGIKEY_CLIENT_ID, "client_secret": DIGIKEY_CLIENT_SECRET, "grant_type": "client_credentials"}
    try:
        resp = requests.post(DK_TOKEN_URL, data=data)
        resp.raise_for_status()
        return resp.json()['access_token']
    except Exception as e:
        raise Exception(f"DigiKey Auth Failed: {e}")

def clean_price(price_val):
    """Converts price value to float, handling None types."""
    if price_val is None: return None
    try: return float(price_val)
    except: return None

def parse_parameters(params_list):
    """Parses product specifications from parameter list."""
    specs = {'k': None, 't': None, 'w': None, 'l': None}
    if not params_list: return specs
    for param in params_list:
        name = param.get('ParameterText', '').lower()
        val = param.get('ValueText', '')
        if 'thermal conductivity' in name: specs['k'] = val
        elif 'thickness' in name or 'height' in name: specs['t'] = val
        elif 'width' in name: specs['w'] = val
        elif 'length' in name and 'lead' not in name: specs['l'] = val
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
def fetch_digikey_data():
    try:
        token = get_digikey_token()
        print(f"DigiKey Token Acquired.")
    except Exception as e:
        print(e)
        return pd.DataFrame()

    # Specific keywords to avoid hitting the 300 item limit
    keywords = [
        "Thermal Grease", "Thermal Paste", "Thermal Pad",
        "Thermal Gap Pad", "Phase Change Material"
    ]
    
    all_rows = []
    print("--- Starting DigiKey API Extraction ---")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": DIGIKEY_CLIENT_ID,
        "X-DIGIKEY-Locale-Site": "TH",      # Force Thai Site
        "X-DIGIKEY-Locale-Currency": "THB", # Force THB Currency
        "Content-Type": "application/json"
    }

    for kw in keywords:
        print(f"Querying: {kw}...")
        offset = 0
        limit = 50
        total_found = 1 
        
        while offset < total_found:
            # Safety Limit per DigiKey Rule (Offset+Limit <= 300)
            if offset + limit > 300:
                print(f"  [Info] Reached 300 items limit for '{kw}'. Next.")
                break 

            body = {
                "Keywords": kw,
                "Limit": limit,
                "Offset": offset,
                "FilterOptionsRequest": {"MarketplaceFilter": "ExcludeMarketPlace"}
            }
            
            try:
                resp = requests.post(DK_SEARCH_URL, json=body, headers=headers)
                
                if resp.status_code == 400: break
                if resp.status_code != 200:
                    print(f"  [Error] API Status {resp.status_code}: {resp.text}")
                    break
                
                data_json = resp.json()
                products = data_json.get('Products', [])
                total_found = data_json.get('ProductsCount', 0)
                
                if not products: break

                for p in products:
                    mpn = p.get('ManufacturerProductNumber')
                    mfr = p.get('Manufacturer', {}).get('Name')
                    
                    # Description parsing
                    desc_obj = p.get('Description', {})
                    desc = desc_obj.get('DetailedDescription') or desc_obj.get('ProductDescription')
                    
                    # Category parsing
                    category = p.get('Category', {}).get('Name')
                    
                    # Spec Parsing
                    params = p.get('Parameters', [])
                    spec_vals = parse_parameters(params)
                    
                    # Fallback Regex Parsing
                    if not spec_vals['t'] or not spec_vals['k']:
                        fallback = extract_from_desc_fallback(desc)
                        spec_vals['t'] = spec_vals['t'] or fallback['t']
                        spec_vals['k'] = spec_vals['k'] or fallback['k']
                        spec_vals['w'] = spec_vals['w'] or fallback['w']
                        spec_vals['l'] = spec_vals['l'] or fallback['l']

                    # --- [pricing fallback] Search in ProductVariations ---
                    price_thb = None
                    variations = p.get('ProductVariations', [])
                    
                    for var in variations:
                        # Find StandardPricing in each Variation
                        pricings = var.get('StandardPricing', [])
                        
                        for pr in pricings:
                            qty = pr.get('BreakQuantity')
                            price_val = pr.get('UnitPrice')
                            
                            # Condition: Retail Quantity (<=10)
                            if qty is not None and qty <= 10:
                                if price_val:
                                    price_thb = clean_price(price_val)
                                    break # Found price, break pricing loop
                        
                        if price_thb: break # Found price, break variations loop

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

                offset += limit
                print(f"  Processed {offset}/{total_found}...")
                time.sleep(1)

            except Exception as e:
                print(f"  [Exception] {e}")
                break
                
    return pd.DataFrame(all_rows)

# -----------------------------------------------------
# EXECUTION
# -----------------------------------------------------
if __name__ == "__main__":
    df = fetch_digikey_data()
    
    if not df.empty:
        df = df[TARGET_COLUMNS]
        df = df.drop_duplicates(subset=['MPN'])
        
        # Ensure data/raw directory exists
        output_dir = os.path.join(os.getcwd(), 'data', 'raw')
        os.makedirs(output_dir, exist_ok=True)
        
        filename = os.path.join(output_dir, "digikey_tim_data.csv")
        df.to_csv(filename, index=False)
        print(f"\nSuccess! Saved {len(df)} items to {filename}")
        try: print(df[['MPN', 'Thickness', 'Price_THB']].head().to_markdown(index=False))
        except: print(df[['MPN', 'Thickness', 'Price_THB']].head())
    else:
        print("No data found.")