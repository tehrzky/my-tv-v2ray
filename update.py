import requests, base64

def get_from_openproxy():
    # The direct link you provided
    url = "https://openproxylist.com/v2ray/rawlist/text"
    
    # This "Header" makes the script look like a real Chrome browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    working = []
    # We only want US servers
    us_markers = ["UNITED STATES", "USA", "US-", "🇺🇸"]

    try:
        # We add 'headers=headers' here to bypass the bot blocker
        r = requests.get(url, headers=headers, timeout=15)
        
        if r.status_code == 200:
            lines = r.text.splitlines()
            for line in lines:
                if len(working) >= 10: break # Grab up to 10
                
                if "vmess://" in line:
                    # Check for US markers
                    if any(m in line.upper() for m in us_markers):
                        working.append(line.strip())
        else:
            print(f"Site blocked us. Status code: {r.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

    if not working:
        return ""

    # Encode for your V2Ray app
    combined = "\n".join(working) + "\n"
    encoded = base64.b64encode(combined.encode('utf-8')).decode('utf-8')
    
    # Fix Padding
    while len(encoded) % 4 != 0: encoded += "="
    return encoded

# Save result
result = get_from_openproxy()
with open("sub.txt", "w") as f:
    f.write(result)
