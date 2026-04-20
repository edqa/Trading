import re

with open("/Users/edwinmaina/Documents/Space/Trading/EM_Futures_Strategy_v5_Tradeify.pine", "r") as f:
    base = f.read()

markets = {
    "CL": {"title": "Crude Oil (CL)", "asia": "false", "ldn": "true", "nyam": "true", "nypm": "false"},
    "GC": {"title": "Gold (GC)", "asia": "false", "ldn": "true", "nyam": "true", "nypm": "false"},
    "NKD": {"title": "Nikkei (NKD)", "asia": "true", "ldn": "true", "nyam": "false", "nypm": "false"},
    "6E_6B": {"title": "Euro/Pound (6E/6B)", "asia": "false", "ldn": "true", "nyam": "true", "nypm": "false"},
    "6J": {"title": "Yen (6J)", "asia": "true", "ldn": "true", "nyam": "false", "nypm": "false"}
}

for sym, data in markets.items():
    content = base
    
    # Update Strategy Title Definition
    content = re.sub(
        r'strategy\("EM Tradeify Prop Strategy v5\.0", shorttitle="EM-FSE Tradeify v5\.0"',
        f'strategy("EM Tradeify Prop Strategy v5.0 - {data["title"]}", shorttitle="EM-FSE {sym}"',
        content
    )
    
    # Update Session Defaults
    content = re.sub(r'sess_asia\s*=\s*input\.bool\((true|false)', f'sess_asia     = input.bool({data["asia"]}', content)
    content = re.sub(r'sess_ldn\s*=\s*input\.bool\((true|false)', f'sess_ldn      = input.bool({data["ldn"]}', content)
    content = re.sub(r'sess_nyAM\s*=\s*input\.bool\((true|false)', f'sess_nyAM     = input.bool({data["nyam"]}', content)
    content = re.sub(r'sess_nyPM\s*=\s*input\.bool\((true|false)', f'sess_nyPM     = input.bool({data["nypm"]}', content)
    
    filename = f"/Users/edwinmaina/Documents/Space/Trading/EM_Futures_Strategy_v5_{sym}.pine"
    with open(filename, "w") as f:
        f.write(content)
        
print("Scripts generated successfully.")
