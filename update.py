import requests, base64, json

def get_5_strict_us():
    url = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    working = []
    
    # These are the only markers we will accept
    us_markers = ["UNITED STATES", "US-", " US ", "🇺🇸", "NEW YORK", "LOS ANGELES", "CHICAGO", "WASHINGTON"]
    
    try:
        r = requests.get(url, timeout=15)
        lines = r.text.splitlines()
        
        for line in lines:
            if len(working) >= 5: break
            
            if "vmess://" in line:
                # Convert line to uppercase to make matching easier
                upper_line = line.upper()
                
                # Check if any US marker is in the line
                if any(marker in upper_line for marker in us_markers):
                    # Double check: ignore common false positives
                    if "RUSSIA" not in upper_line and "BELARUS" not in upper_line:
                        working.append(line.strip())
                    
    except:
        pass
        
    if not working: return ""
    
    combined_text = "\n".join(working)
    return base64.b64encode(combined_text.encode('utf-8')).decode('utf-8')

result = get_5_strict_us()
with open("sub.txt", "w") as f:
    f.write(result)
