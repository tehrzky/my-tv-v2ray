import requests, base64, json

def get_strict_us_openproxy():
    # Use the reliable GitHub mirror of openproxylist
    url = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    working = []
    
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            for line in r.text.splitlines():
                if not line.startswith("vmess://"): continue
                
                try:
                    # 1. Unpack the VMess box
                    b64_part = line.split("vmess://")[1]
                    # Add padding if missing so it doesn't crash
                    decoded_json = base64.b64decode(b64_part + "==").decode('utf-8')
                    data = json.loads(decoded_json)
                    
                    # 2. Check the 'ps' (Remarks) field for your US info
                    remarks = str(data.get('ps', '')).upper()
                    
                    # We look for the flag or the US text you specified
                    if "🇺🇸" in remarks or "VMESS-US" in remarks or "UNITED STATES" in remarks:
                        working.append(line.strip())
                except:
                    continue
    except:
        pass

    if not working:
        return ""

    # 3. Pack them back up for the TV
    combined = "\n".join(working) + "\n"
    encoded = base64.b64encode(combined.encode('utf-8')).decode('utf-8')
    
    # Final padding check for v2rayNG
    while len(encoded) % 4 != 0:
        encoded += "="
    return encoded

# Save result
result = get_strict_us_openproxy()
with open("sub.txt", "w") as f:
    f.write(result)
