import requests, base64, json, socket

def is_online(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=2): return True
    except: return False

def get_5_us():
    working = []
    # Source link from OpenProxyList
    r = requests.get("https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt")
    for line in r.text.splitlines():
        if len(working) >= 5: break
        if "vmess://" in line and any(tag in line for tag in ["US", "United States", "🇺🇸"]):
            try:
                # Basic check to see if server responds
                config = json.loads(base64.b64decode(line.split("vmess://")[1] + '===').decode('utf-8'))
                if is_online(config['add'], config['port']):
                    working.append(line)
            except: continue
    return base64.b64encode("\n".join(working).encode('utf-8')).decode('utf-8')

with open("sub.txt", "w") as f:
    f.write(get_5_us())
  
