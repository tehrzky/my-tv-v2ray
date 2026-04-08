import requests, base64

def get_5_us_vmess():
    url = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    working = []
    
    try:
        r = requests.get(url, timeout=15)
        lines = r.text.splitlines()
        
        for line in lines:
            if len(working) >= 5: break
            # Search for VMess + US tags
            if "vmess://" in line and any(tag in line.upper() for tag in ["US", "UNITED STATES", "🇺🇸"]):
                working.append(line.strip())
                    
    except:
        pass
        
    if not working:
        return ""
        
    # Standard V2Ray subscription format: links separated by newlines
    combined_text = "\n".join(working)
    
    # Standard Base64 encoding
    encoded_bytes = base64.b64encode(combined_text.encode('utf-8'))
    return encoded_bytes.decode('utf-8')

# Save the result
result = get_5_us_vmess()
with open("sub.txt", "w") as f:
    f.write(result)
