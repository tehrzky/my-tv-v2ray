import requests, base64, json

def get_5_us_vmess():
    # Multiple sources to ensure we never get an empty file
    sources = [
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
        "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/V2Ray-Config-By-EbraSha-All-Type.txt",
        "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/Splitted-By-Protocol/vmess.txt"
    ]
    
    working = []
    us_keywords = ["UNITED STATES", "USA", "US-", "NEW YORK", "LOS ANGELES", "CHICAGO", "🇺🇸"]

    for url in sources:
        try:
            r = requests.get(url, timeout=10)
            lines = r.text.splitlines()
            for line in lines:
                if len(working) >= 5: break
                
                # Check for VMess
                if line.startswith("vmess://"):
                    # Check if the raw line contains US markers
                    if any(k in line.upper() for k in us_keywords):
                        working.append(line.strip())
                    else:
                        # Deep check: decode it to see if US is hidden inside
                        try:
                            b64_data = line.replace("vmess://", "")
                            decoded = json.loads(base64.b64decode(b64_data + "==").decode('utf-8'))
                            ps = str(decoded.get('ps', '')).upper()
                            if any(k in ps for k in us_keywords):
                                working.append(line.strip())
                        except:
                            continue
        except:
            continue
            
    if not working:
        return ""
    
    # Return as Base64 for your TV app
    return base64.b64encode("\n".join(working).encode('utf-8')).decode('utf-8')

# Save result
result = get_5_us_vmess()
with open("sub.txt", "w") as f:
    f.write(result)
