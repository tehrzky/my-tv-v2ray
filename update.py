import asyncio
import base64
import ipaddress
import json
import logging
import re
import socket
import time
import urllib.parse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

SOURCES = [
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/refs/heads/main/vless_configs.txt",
]
OUTPUT_FILE = "sub.txt"
MAX_RESULTS = 20
MAX_WORKERS = 32
REQ_TIMEOUT = 15
TCP_TIMEOUT = 2.0
GEO_BATCH = 50

CF_RANGES = [ipaddress.ip_network(n) for n in [
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17",
]]

US_MARKERS = re.compile(
    r"(🇺🇸|\[US\]|\(US\)|\bUS[-_ ]?\d|\bUSA?\b|UNITED[ _-]?STATES|"
    r"AMERICA|LAX|SFO|SEA\d|NYC|CHI\d|MIA|DAL|ATL|PHX|DEN|BOS|"
    r"CALIFORNIA|TEXAS|NEW[ _-]?YORK|FLORIDA|VIRGINIA|VERMONT|"
    r"OREGON|OHIO|NEVADA)",
    re.IGNORECASE)

NEG_MARKERS = re.compile(
    r"(🇮🇷|🇩🇪|🇫🇷|🇳🇱|🇬🇧|🇹🇷|🇷🇺|🇨🇳|🇭🇰|🇸🇬|🇯🇵|🇰🇷|🇮🇳|"
    r"\bDE[-_ ]|\bFR[-_ ]|\bNL[-_ ]|\bUK[-_ ]|\bTR[-_ ]|\bRU[-_ ]|"
    r"\bIR[-_ ]|\bIRAN|GERMANY|FRANCE|NETHERLAND|TURKEY|RUSSIA)",
    re.IGNORECASE)

def is_cloudflare(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return any(a in net for net in CF_RANGES)
    except ValueError:
        return False

def parse_vless(line: str) -> Optional[dict]:
    try:
        body = line[8:]
        fragment = ""
        if "#" in body:
            body, fragment = body.split("#", 1)
            fragment = urllib.parse.unquote(fragment)
        if "@" not in body:
            return None
        uuid, hostport = body.rsplit("@", 1)
        query = ""
        if "?" in hostport:
            hostport, query = hostport.split("?", 1)
        hostport = hostport.rstrip("/")

        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
            port = int(port)
        else:
            host, port = hostport, 443

        params = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()} if query else {}
        return {
            "proto": "vless",
            "id": urllib.parse.unquote(uuid),
            "add": host,
            "port": port,
            "ps": fragment,
            "raw": line,
        }
    except Exception:
        return None

def parse_vmess(line: str) -> Optional[dict]:
    try:
        payload = line[8:]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        decoded = base64.urlsafe_b64decode(payload).decode("utf-8", errors="ignore")
        cfg = json.loads(decoded)
        if not cfg.get("add") or not cfg.get("port"):
            return None
        return {
            "proto": "vmess",
            "id": cfg.get("id"),
            "add": cfg.get("add"),
            "port": int(cfg.get("port")),
            "ps": cfg.get("ps", ""),
            "raw": line,
        }
    except Exception:
        return None

def parse_line(line: str) -> Optional[dict]:
    line = line.strip()
    if line.startswith("vless://"):
        return parse_vless(line)
    if line.startswith("vmess://"):
        return parse_vmess(line)
    return None

def fetch_source(url: str) -> list[str]:
    try:
        r = requests.get(url, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        text = r.text.strip()
        
        # Base64 decoded check
        if not text.startswith("vless://") and not text.startswith("vmess://"):
            try:
                decoded = base64.b64decode(text).decode("utf-8", errors="ignore")
                if "vless://" in decoded or "vmess://" in decoded:
                    text = decoded
            except Exception:
                pass

        lines = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(("vless://", "vmess://")):
                lines.append(line)
        return lines
    except Exception as e:
        log.error(f"Failed fetching {url}: {e}")
        return []

def resolve_host(host: str) -> Optional[str]:
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        socket.setdefaulttimeout(3.0)
        return socket.gethostbyname(host)
    except socket.error:
        return None

def batch_geo(ips: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not ips:
        return out
        
    for i in range(0, len(ips), GEO_BATCH):
        batch = ips[i:i + GEO_BATCH]
        payload = [{"query": ip} for ip in batch]
        
        for attempt in range(2):
            try:
                r = requests.post(
                    "http://ip-api.com/batch?fields=countryCode,query",
                    json=payload, 
                    timeout=10
                )
                if r.status_code == 429:
                    time.sleep(3)
                    continue
                r.raise_for_status()
                for item in r.json():
                    out[item["query"]] = item.get("countryCode", "").upper()
                break
            except Exception as e:
                log.warning(f"Geo batch failure: {e}")
                time.sleep(1)
    return out

def tcp_alive(host: str, port: int, timeout: float = TCP_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def main() -> Optional[str]:
    raw_lines = []
    for url in SOURCES:
        raw_lines.extend(fetch_source(url))
    log.info(f"Total raw lines fetched: {len(raw_lines)}")

    parsed = [c for c in (parse_line(l) for l in raw_lines) if c]
    log.info(f"Successfully parsed: {len(parsed)}")

    seen = OrderedDict()
    for c in parsed:
        key = (c["proto"], c["id"], c["add"], c["port"])
        seen.setdefault(key, c)
    configs = list(seen.values())
    log.info(f"Unique configurations: {len(configs)}")

    by_remark = []
    candidates = []
    for c in configs:
        text = f"{c.get('ps','')} {c.get('add','')}"
        if US_MARKERS.search(text) and not NEG_MARKERS.search(text):
            by_remark.append(c)
        else:
            candidates.append(c)
    log.info(f"US matched by remark: {len(by_remark)} | Geo candidates remaining: {len(candidates)}")

    # Resolve hosts
    hosts = list({c["add"] for c in candidates})
    host_ip: dict[str, str] = {}
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(resolve_host, h): h for h in hosts}
        for f in as_completed(futs):
            h = futs[f]
            ip = f.result()
            if ip:
                host_ip[h] = ip

    # Map candidate via add domain/ip directly instead of internal object memory id
    ips_to_check = []
    for c in candidates:
        ip = host_ip.get(c["add"])
        if ip and not is_cloudflare(ip):
            c["resolved_ip"] = ip
            ips_to_check.append(ip)

    uniq_ips = list(set(ips_to_check))
    log.info(f"Resolving geo location for {len(uniq_ips)} IPs...")
    geo = batch_geo(uniq_ips)

    by_geo = [
        c for c in candidates 
        if c.get("resolved_ip") and geo.get(c["resolved_ip"]) == "US"
    ]
    log.info(f"US matched by IP Geo: {len(by_geo)}")

    combined_configs = list({c["raw"]: c for c in (by_remark + by_geo)}.values())
    log.info(f"Total candidates combined: {len(combined_configs)}")

    def check(cfg):
        return cfg["raw"], tcp_alive(cfg["add"], cfg["port"])

    alive = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(check, c) for c in combined_configs]
        for f in as_completed(futs):
            raw, ok = f.result()
            if ok:
                alive.append(raw)
                
    log.info(f"Alive endpoints after TCP latency verification: {len(alive)}")

    final_src = alive if len(alive) > 0 else [c["raw"] for c in combined_configs]
    final = final_src[:MAX_RESULTS]

    if not final:
        log.warning("No configs remained after filtering.")
        return ""
        
    out = "\n".join(final) + "\n"
    return base64.b64encode(out.encode()).decode()

if __name__ == "__main__":
    try:
        r = main()
        if r is None or r == "":
            log.error("Execution completed, but generated subscription payload was empty.")
        else:
            with open(OUTPUT_FILE, "w") as f:
                f.write(r)
            log.info(f"Wrote {OUTPUT_FILE} ({len(r)} b64 chars)")
    except Exception as e:
        log.exception(f"Fatal error encountered: {e}")
