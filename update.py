import requests, base64

def get_5_us_vmess():
    # Source link
    url = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    working = []
    
    try:
        r = requests.get(url, timeout=15)
        lines = r.text.splitlines()
        
        for line in lines:
            if len(working) >= 5:
                break
            
            # This looks for US, United States, or the US Flag emoji anywhere in the link
            if "vmess://" in line:
                if any(target in line.upper() for target in ["US", "UNITED STATES", "🇺🇸"]):
                    working.append(line.strip())
                    
    except Exception as e:
        print(f"Error: {e}")
        
    if not working:
        return ""
        
    # Join with newlines and encode
    combined_text = "\n".join(working)
    return base64.b64encode(combined_text.encode('utf-8')).decode('utf-8')

# Save the result
result = get_5_us_vmess()
with open("sub.txt", "w") as f:
    f.write(result)
