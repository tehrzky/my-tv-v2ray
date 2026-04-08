import requests, base64

def get_5_us_vmess():
    # These are MIRRORS that GitHub doesn't block
    sources = [
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt", # Mirror of openproxylist
        "https://raw.githubusercontent.com/vfarid/v2ray-share/main/all_links.txt",
        "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Splitted-By-Protocol/vmess.txt"
    ]
    
    working = []
    us_markers = ["UNITED STATES", "USA", "US-", "🇺🇸"]

    for url in sources:
        try:
            # We don't need fancy headers for GitHub-to-GitHub links
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if len(working) >= 10: break
                    line = line.strip()
                    if line.startswith("vmess://") and any(m in line.upper() for m in us_markers):
                        working.append(line)
        except: continue
            
    if not working: return ""
    
    # Standard V2Ray Base64 encoding
    combined = "\n".join(working) + "\n"
    encoded = base64.b64encode(combined.encode('utf-8')).decode('utf-8')
    
    # Fix Padding for your TV
    while len(encoded) % 4 != 0: encoded += "="
    return encoded

# Save result
result = get_5_us_vmess()
with open("sub.txt", "w") as f:
    f.write(result)
