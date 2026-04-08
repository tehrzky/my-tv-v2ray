import requests, base64, json

def get_5_us_vmess():
    working = []
    # Using the raw GitHub source of OpenProxyList for better reliability
    url = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    
    try:
        r = requests.get(url, timeout=15)
        lines = r.text.splitlines()
        
        for line in lines:
            if len(working) >= 5: break
            
            # 1. Must be vmess
            # 2. Must contain US or United States or the US Flag
            if line.startswith("vmess://") and any(x in line for x in ["US", "United States", "🇺🇸"]):
                working.append(line)
                
    except Exception as e:
        print(f"Error: {e}")
        
    if not working:
        return ""
        
    # Join the 5 links with newlines and encode to Base64
    combined = "\n".join(working)
    return base64.b64encode(combined.encode('utf-8')).decode('utf-8')

# Save to sub.txt
output = get_5_us_vmess()
with open("sub.txt", "w") as f:
    f.write(output)
