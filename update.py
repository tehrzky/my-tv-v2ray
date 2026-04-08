import requests

def get_5_us_vmess_plain():
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
                # Check for vmess and US markers
                if line.startswith("vmess://") and any(k in line.upper() for k in us_keywords):
                    working.append(line)
        except: continue
            
    # Return the links joined by a new line (NOT encoded)
    return "\n".join(working)

# Save result
result = get_5_us_vmess_plain()
with open("sub.txt", "w") as f:
    f.write(result)
