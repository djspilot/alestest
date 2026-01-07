import pandas as pd
import os

excel_path = '/Users/ds/Projecten/alestest/parts/AI-voorbeelden/20251145/20251145.xls'
search_terms = ['10040852', '10040853', 'MD-06-2-008399', 'MD-19-06774']

try:
    df = pd.read_excel(excel_path, header=None)
    print(f"Loaded Excel with shape: {df.shape}")
    
    found = False
    for term in search_terms:
        # Search in the entire dataframe
        mask = df.applymap(lambda x: term in str(x) if pd.notnull(x) else False)
        if mask.any().any():
            print(f"Found '{term}' in Excel!")
            # Print the row(s)
            rows = df[mask.any(axis=1)]
            print(rows.to_string())
            found = True
            
    if not found:
        print("No part numbers found in Excel.")
        
except Exception as e:
    print(f"Error reading Excel: {e}")
