import requests, base64, json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_strict_us_openproxy():
    url = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
    working = []
    
    try:
        logger.info(f"Fetching proxies from {url}")
        r = requests.get(url, timeout=15)
        r.raise_for_status()  # Raise exception for bad status codes
        
        logger.info(f"Downloaded {len(r.text)} bytes")
        for line_num, line in enumerate(r.text.splitlines(), 1):
            if not line.startswith("vmess://"): 
                continue
            
            try:
                b64_part = line.split("vmess://")[1]
                decoded_json = base64.b64decode(b64_part + "==").decode('utf-8')
                data = json.loads(decoded_json)
                
                remarks = str(data.get('ps', '')).upper()
                
                if "🇺🇸" in remarks or "VMESS-US" in remarks or "UNITED STATES" in remarks:
                    working.append(line.strip())
            except Exception as e:
                logger.warning(f"Failed to parse line {line_num}: {e}")
                continue
                
    except requests.RequestException as e:
        logger.error(f"Failed to fetch proxy list: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

    if not working:
        logger.warning("No US proxies found!")
        return ""

    logger.info(f"Found {len(working)} US proxies")
    combined = "\n".join(working) + "\n"
    encoded = base64.b64encode(combined.encode('utf-8')).decode('utf-8')
    
    while len(encoded) % 4 != 0:
        encoded += "="
    
    return encoded

# Save result
try:
    result = get_strict_us_openproxy()
    if result is not None:
        with open("sub.txt", "w") as f:
            f.write(result)
        logger.info("Update successful")
    else:
        logger.error("Update failed - check logs above")
except Exception as e:
    logger.error(f"Failed to write output: {e}")
