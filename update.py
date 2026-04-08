import requests, base64

def get_stable_sub():
    url = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    working = []
    
    try:
        r = requests.get(url, timeout=15)
        for line in r.text.splitlines():
            if len(working) >= 15: break
            if "vmess://" in line:
                working.append(line.strip())
    except:
        pass

    if not working: return ""

    # Combine and Encode
    combined = "\n".join(working)
    # tr -d '\n' equivalent: ensures it is a single solid block
    encoded = base64.b64encode(combined.encode('utf-8')).decode('utf-8').replace("\n", "").replace("\r", "")
    
    # Force Correct Padding
    missing_padding = len(encoded) % 4
    if missing_padding:
        encoded += '=' * (4 - missing_padding)
        
    return encoded

# Save
result = get_stable_sub()
with open("sub.txt", "w") as f:
    f.write(result)
