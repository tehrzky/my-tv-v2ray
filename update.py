import requests, base64

def get_vmess_configs():
    # Using the GitHub Mirror which is reliable and updated
    url = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    
    working = []
    # We'll prioritize US, but take others so the file isn't empty
    us_markers = ["UNITED STATES", "USA", "US-", "🇺🇸"]
    
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            lines = r.text.splitlines()
            
            # First pass: Grab US servers
            for line in lines:
                if len(working) >= 5: break
                if "vmess://" in line and any(m in line.upper() for m in us_markers):
                    working.append(line.strip())
            
            # Second pass: If we don't have 5 yet, grab whatever is available
            if len(working) < 5:
                for line in lines:
                    if len(working) >= 10: break
                    if "vmess://" in line and line.strip() not in working:
                        working.append(line.strip())
                        
    except Exception as e:
        print(f"Error: {e}")

    if not working:
        return ""

    # Join with newlines and encode for V2Ray
    combined = "\n".join(working) + "\n"
    encoded = base64.b64encode(combined.encode('utf-8')).decode('utf-8')
    
    # Fix Padding (Crucial for TV apps)
    while len(encoded) % 4 != 0:
        encoded += "="
        
    return encoded

# Save the result to sub.txt
result = get_vmess_configs()
with open("sub.txt", "w") as f:
    f.write(result)
