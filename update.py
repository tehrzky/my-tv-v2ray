import requests, base64

def get_5_us_vmess():
    # Adding fresh 2026 sources
    sources = [
        "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/super-sub.txt",
        "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Splitted-By-Protocol/vmess.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    ]
    
    found_us = []
    backup_all = []
    us_keywords = ["UNITED STATES", "USA", "US-", "NEW YORK", "LOS ANGELES", "CHICAGO", "🇺🇸"]

    for url in sources:
        try:
            r = requests.get(url, timeout=10)
            # Some sources are already Base64, we need to decode them first
            content = r.text
            try:
                content = base64.b64decode(content).decode('utf-8')
            except:
                pass # It was already plain text
                
            for line in content.splitlines():
                line = line.strip()
                if not line.startswith("vmess://"): continue
                
                # Keep everything as a backup
                if len(backup_all) < 10: backup_all.append(line)
                
                # Filter for US
                if any(k in line.upper() for k in us_keywords):
                    if len(found_us) < 5: found_us.append(line)
        except: continue
            
    # Priority: 1. US Servers, 2. Backup Servers, 3. Empty String
    final_list = found_us if found_us else backup_all
    
    if not final_list: return ""
    
    # Standard V2Ray Base64 encoding
    combined_text = "\n".join(final_list) + "\n"
    encoded_str = base64.b64encode(combined_text.encode('utf-8')).decode('utf-8')
    
    # Ensure correct padding
    while len(encoded_str) % 4 != 0: encoded_str += "="
    return encoded_str

# Save
result = get_5_us_vmess()
with open("sub.txt", "w") as f:
    f.write(result)
