import requests
import base64
import json
import re
import socket
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from collections import OrderedDict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
SOURCE_URL = "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"
OUTPUT_FILE = "sub.txt"
MAX_WORKERS = 32
REQUEST_TIMEOUT = 15
GEO_TIMEOUT = 20

# Expanded US indicators in remarks (ps field)
US_REMARK_PATTERNS = re.compile(
    r"\b(US|USA|UNITED[ _-]?STATES|AMERICA|AMERICAN|"
    r"LAX|SFO|SEA|NYC|CHI|MIA|DAL|ATL|PHX|DEN|BOS|"
    r"CALIFORNIA|TEXAS|NEW[ _-]?YORK|FLORIDA|VIRGINIA|"
    r"VERMONT|OREGON|OHIO|NEVADA|NEVADA|"
    r"🇺🇸|U\.S\.A?)\b",
    re.IGNORECASE
)

# ── Helpers ────────────────────────────────────────────────────────────────

def decode_vmess(line: str) -> dict | None:
    """Robustly decode a vmess:// URL to its JSON config."""
    if not line.startswith("vmess://"):
        return None
    b64_part = line[8:]  # strip "vmess://"
    try:
        # Proper padding handling
        pad = 4 - len(b64_part) % 4
        if pad != 4:
            b64_part += "=" * pad
        decoded = base64.urlsafe_b64decode(b64_part).decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        logger.debug(f"Decode failed: {e}")
        return None


def is_us_by_remark(cfg: dict) -> bool:
    """Check if the proxy name/remarks indicate US."""
    ps = str(cfg.get("ps", ""))
    add = str(cfg.get("add", ""))
    return bool(US_REMARK_PATTERNS.search(ps)) or bool(US_REMARK_PATTERNS.search(add))


def resolve_host(host: str) -> str | None:
    """Resolve domain to IPv4; return IP if already an IP."""
    # Quick IP check
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host):
        return host
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return None


def batch_geolocation(ips: list[str]) -> dict[str, str]:
    """
    Query ip-api.com batch endpoint (free, 100 IPs per request).
    Returns {ip: country_code}.
    """
    if not ips:
        return {}

    results = {}
    # ip-api free batch limit is 100 per request
    for i in range(0, len(ips), 100):
        batch = ips[i:i+100]
        try:
            r = requests.post(
                "http://ip-api.com/batch?fields=countryCode,query",
                json=batch,
                timeout=GEO_TIMEOUT,
                headers={"Content-Type": "application/json"}
            )
            r.raise_for_status()
            for item in r.json():
                ip = item.get("query")
                cc = item.get("countryCode", "").upper()
                if ip:
                    results[ip] = cc
        except Exception as e:
            logger.warning(f"Batch geolocation failed for chunk {i//100}: {e}")
    return results


def is_valid_cfg(cfg: dict) -> bool:
    """Ensure the config has the minimum required fields."""
    required = ("add", "port", "id", "net")
    return all(cfg.get(k) for k in required)


# ── Main ───────────────────────────────────────────────────────────────────

def fetch_and_filter_us_proxies() -> str | None:
    logger.info(f"Fetching proxy list from {SOURCE_URL}")
    try:
        r = requests.get(SOURCE_URL, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch source: {e}")
        return None

    lines = [ln.strip() for ln in r.text.splitlines() if ln.strip().startswith("vmess://")]
    logger.info(f"Total vmess lines: {len(lines)}")

    # ── 1. Decode & validate ─────────────────────────────────────────────
    parsed = []
    for line in lines:
        cfg = decode_vmess(line)
        if cfg and is_valid_cfg(cfg):
            parsed.append((line, cfg))

    logger.info(f"Valid configs: {len(parsed)}")

    # ── 2. Deduplicate by server:port ────────────────────────────────────
    seen = OrderedDict()
    for line, cfg in parsed:
        key = f"{cfg['add']}:{cfg['port']}"
        if key not in seen:
            seen[key] = (line, cfg)
    unique = list(seen.values())
    logger.info(f"Unique server:port combos: {len(unique)}")

    # ── 3. Fast-path: remark-based US filtering ──────────────────────────
    remark_us = []
    to_geo_check = []
    for line, cfg in unique:
        if is_us_by_remark(cfg):
            remark_us.append(line)
        else:
            to_geo_check.append((line, cfg))

    logger.info(f"US by remarks: {len(remark_us)} | To geo-check: {len(to_geo_check)}")

    # ── 4. Resolve domains → IPs in parallel ─────────────────────────────
    host_to_ip = {}
    hosts_to_resolve = list({cfg["add"] for _, cfg in to_geo_check})
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        future_to_host = {ex.submit(resolve_host, h): h for h in hosts_to_resolve}
        for future in as_completed(future_to_host):
            host = future_to_host[future]
            ip = future.result()
            if ip:
                host_to_ip[host] = ip

    # Map configs to their resolved IPs
    ip_mapped = []
    unresolved = 0
    for line, cfg in to_geo_check:
        ip = host_to_ip.get(cfg["add"])
        if ip:
            ip_mapped.append((line, ip))
        else:
            unresolved += 1

    if unresolved:
        logger.warning(f"Could not resolve {unresolved} hosts")

    # ── 5. Batch IP geolocation ──────────────────────────────────────────
    unique_ips = list({ip for _, ip in ip_mapped})
    logger.info(f"Querying geolocation for {len(unique_ips)} unique IPs...")
    geo_map = batch_geolocation(unique_ips)

    geo_us = []
    for line, ip in ip_mapped:
        if geo_map.get(ip) == "US":
            geo_us.append(line)

    logger.info(f"US by geolocation: {len(geo_us)}")

    # ── 6. Combine & encode ──────────────────────────────────────────────
    final = remark_us + geo_us
    if not final:
        logger.warning("No US proxies found!")
        return ""

    # Deduplicate one last time (remark + geo might overlap)
    final_unique = list(OrderedDict.fromkeys(final))
    logger.info(f"Final US proxy count: {len(final_unique)}")

    combined = "\n".join(final_unique) + "\n"
    encoded = base64.b64encode(combined.encode("utf-8")).decode("utf-8")
    return encoded


# ── Run ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        result = fetch_and_filter_us_proxies()
        if result is not None:
            with open(OUTPUT_FILE, "w") as f:
                f.write(result)
            logger.info(f"Saved {OUTPUT_FILE} successfully")
        else:
            logger.error("Update failed")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
