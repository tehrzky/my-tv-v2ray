import requests
import base64
import json
import re
import socket
import logging
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
SOURCES = [
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Splitted-By-Protocol/vmess.txt",
]
OUTPUT_FILE = "sub.txt"
MAX_RESULTS = 20
MAX_WORKERS = 32
REQUEST_TIMEOUT = 15
GEO_TIMEOUT = 20

# Expanded US indicators
US_REMARK_PATTERNS = re.compile(
    r"\b(US|USA|UNITED[ _-]?STATES|AMERICA|AMERICAN|"
    r"LAX|SFO|SEA|NYC|CHI|MIA|DAL|ATL|PHX|DEN|BOS|"
    r"CALIFORNIA|TEXAS|NEW[ _-]?YORK|FLORIDA|VIRGINIA|"
    r"VERMONT|OREGON|OHIO|NEVADA|"
    r"🇺🇸|U\.S\.A?)\b",
    re.IGNORECASE
)

# ── Helpers ────────────────────────────────────────────────────────────────

def decode_vmess(line: str) -> dict | None:
    """Decode vmess:// URL to JSON config. Handles both base64-JSON and URI formats."""
    if not line.startswith("vmess://"):
        return None
    payload = line[8:]

    # ── Try base64 JSON first ─────────────────────────────────────────────
    try:
        pad = 4 - len(payload) % 4
        if pad != 4:
            payload += "=" * pad
        decoded = base64.urlsafe_b64decode(payload).decode("utf-8")
        cfg = json.loads(decoded)
        if cfg.get("add") and cfg.get("port"):
            return cfg
    except Exception:
        pass

    # ── Try URI format: vmess://uuid@host:port?params#remark ──────────────
    try:
        # Split fragment (remark/ps)
        if "#" in payload:
            body, remark = payload.split("#", 1)
            remark = urllib.parse.unquote(remark)
        else:
            body, remark = payload, ""

        # Parse userinfo@host:port
        if "@" not in body:
            return None
        userinfo, hostport = body.rsplit("@", 1)
        uuid = urllib.parse.unquote(userinfo)

        # Parse host:port
        if ":" in hostport:
            host, port_str = hostport.rsplit(":", 1)
            port = int(port_str)
        else:
            host, port = hostport, 443

        # Parse query params
        if "?" in host:
            host, query = host.split("?", 1)
            params = urllib.parse.parse_qs(query)
        else:
            params = {}

        net = params.get("type", ["tcp"])[0]
        tls = params.get("security", [""])[0]
        path = urllib.parse.unquote(params.get("path", ["/"])[0])
        host_header = urllib.parse.unquote(params.get("host", [""])[0])
        sni = urllib.parse.unquote(params.get("sni", [""])[0])

        return {
            "v": "2",
            "ps": remark,
            "add": host,
            "port": str(port),
            "id": uuid,
            "aid": "0",
            "scy": "auto",
            "net": net,
            "type": "none",
            "host": host_header,
            "path": path,
            "tls": tls,
            "sni": sni,
        }
    except Exception as e:
        logger.debug(f"URI parse failed: {e}")
        return None


def is_us_by_remark(cfg: dict) -> bool:
    ps = str(cfg.get("ps", ""))
    add = str(cfg.get("add", ""))
    return bool(US_REMARK_PATTERNS.search(ps)) or bool(US_REMARK_PATTERNS.search(add))


def resolve_host(host: str) -> str | None:
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host):
        return host
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return None


def batch_geolocation(ips: list[str]) -> dict[str, str]:
    if not ips:
        return {}
    results = {}
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
            logger.warning(f"Geo batch {i//100} failed: {e}")
    return results


def is_valid_cfg(cfg: dict) -> bool:
    return all(cfg.get(k) for k in ("add", "port", "id", "net"))


def fetch_source(url: str) -> list[str]:
    """Fetch a source and return list of vmess:// lines."""
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        text = r.text

        # Some subscriptions wrap the whole file in base64
        if not text.strip().startswith("vmess://"):
            try:
                text = base64.b64decode(text).decode("utf-8")
            except Exception:
                pass

        lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("vmess://")]
        logger.info(f"{url}: {len(lines)} vmess lines")
        return lines
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return []


# ── Main ───────────────────────────────────────────────────────────────────

def fetch_and_filter_us_proxies() -> str | None:
    # ── 1. Fetch all sources ───────────────────────────────────────────────
    all_lines = []
    for url in SOURCES:
        all_lines.extend(fetch_source(url))
    logger.info(f"Total vmess lines from all sources: {len(all_lines)}")

    # ── 2. Decode & validate ─────────────────────────────────────────────
    parsed = []
    for line in all_lines:
        cfg = decode_vmess(line)
        if cfg and is_valid_cfg(cfg):
            parsed.append((line, cfg))

    logger.info(f"Valid configs: {len(parsed)}")

    # ── 3. Deduplicate by server:port ────────────────────────────────────
    seen = OrderedDict()
    for line, cfg in parsed:
        key = f"{cfg['add']}:{cfg['port']}"
        if key not in seen:
            seen[key] = (line, cfg)
    unique = list(seen.values())
    logger.info(f"Unique server:port combos: {len(unique)}")

    # ── 4. Fast-path remark filtering ────────────────────────────────────
    remark_us = []
    to_geo_check = []
    for line, cfg in unique:
        if is_us_by_remark(cfg):
            remark_us.append(line)
        else:
            to_geo_check.append((line, cfg))

    logger.info(f"US by remarks: {len(remark_us)} | To geo-check: {len(to_geo_check)}")

    # ── 5. Resolve domains → IPs in parallel ─────────────────────────────
    host_to_ip = {}
    hosts_to_resolve = list({cfg["add"] for _, cfg in to_geo_check})
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        future_to_host = {ex.submit(resolve_host, h): h for h in hosts_to_resolve}
        for future in as_completed(future_to_host):
            host = future_to_host[future]
            ip = future.result()
            if ip:
                host_to_ip[host] = ip

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

    # ── 6. Batch IP geolocation ──────────────────────────────────────────
    unique_ips = list({ip for _, ip in ip_mapped})
    logger.info(f"Querying geolocation for {len(unique_ips)} unique IPs...")
    geo_map = batch_geolocation(unique_ips)

    geo_us = []
    for line, ip in ip_mapped:
        if geo_map.get(ip) == "US":
            geo_us.append(line)

    logger.info(f"US by geolocation: {len(geo_us)}")

    # ── 7. Combine, dedup, and enforce 20-max limit ──────────────────────
    # Remark-matched entries get priority (more likely intentionally US)
    combined = list(OrderedDict.fromkeys(remark_us + geo_us))
    
    if not combined:
        logger.warning("No US proxies found!")
        return ""

    logger.info(f"Total US proxies before limit: {len(combined)}")
    
    final = combined[:MAX_RESULTS]
    logger.info(f"Final US proxy count (max {MAX_RESULTS}): {len(final)}")

    # ── 8. Encode output ─────────────────────────────────────────────────
    out_text = "\n".join(final) + "\n"
    encoded = base64.b64encode(out_text.encode("utf-8")).decode("utf-8")
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
