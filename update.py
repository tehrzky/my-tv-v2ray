import requests, base64

def get_5_us_vmess_base64():
    sources = [
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
        "https://raw.githubusercontent.com/vfarid/v2ray-share/main/all_links.txt",
        "https://raw.githubusercontent.com/mue007/v2ray-free/main/v2ray"
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
    
    # 1. Join links with a NEW LINE at the end of the last link (V2Ray standard)
    combined_text = "\n".join(working) + "\n"
    
    # 2. Encode to Base64
    encoded_bytes = base64.b64encode(combined_text.encode('utf-8'))
    encoded_str = encoded_bytes.decode('utf-8')
    
    # 3. Final cleanup: Remove any accidental spaces
    return encoded_str.strip()

# Save result
result = get_5_us_vmess_base64()
with open("sub.txt", "w") as f:
    f.write(result)
