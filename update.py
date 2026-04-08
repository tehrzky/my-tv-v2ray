import requests, base64

def get_5_us_vmess():
    sources = [
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
        "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/V2Ray-Config-By-EbraSha-All-Type.txt",
        "https://raw.githubusercontent.com/vfarid/v2ray-share/main/all_links.txt"
    ]
    
    working = []
    us_keywords = ["UNITED STATES", "USA", "US-", "NEW YORK", "🇺🇸"]

    for url in sources:
        try:
            r = requests.get(url, timeout=10)
            for line in r.text.splitlines():
                if len(working) >= 5: break
                line = line.strip()
                if line.startswith("vmess://") and any(k in line.upper() for k in us_keywords):
                    working.append(line)
        except: continue
            
    if not working: return ""
    
    # 1. Join with simple newlines
    combined_text = "\n".join(working)
    
    # 2. Encode to Base64
    encoded_bytes = base64.b64encode(combined_text.encode('utf-8'))
    encoded_str = encoded_bytes.decode('utf-8')
    
    # 3. FIX PADDING (The most important part for TV apps)
    # Base64 length must be a multiple of 4
    while len(encoded_str) % 4 != 0:
        encoded_str += "="
        
    return encoded_str

# Save result
result = get_5_us_vmess()
with open("sub.txt", "w") as f:
    f.write(result)
