import asyncio
import base64
import ipaddress
import json
import logging
import re
import socket
import urllib.parse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

SOURCES = [
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/refs/heads/main/vless_configs.txt",
]
OUTPUT_FILE = "sub.txt"
MAX_RESULTS = 20
MAX_WORKERS = 32
REQ_TIMEOUT = 20
TCP_TIMEOUT = 2.0           # seconds for connect test
GEO_BATCH = 100

# ── Cloudflare / known anycast ranges: geo lies about these ──────────────
CF_RANGES = [ipaddress.ip_network(n) for n in [
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17",
]]

def is_cloudflare(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a in net for net in CF_RANGES)

# ── Strong US markers ─────────────────────────────────────────────────────
US_MARKERS = re.compile(
    r"(🇺🇸|\[US\]|\(US\)|\bUS[-_ ]?\d|\bUSA?\b|UNITED[ _-]?STATES|"
    r"AMERICA|LAX|SFO|SEA\d|NYC|CHI\d|MIA|DAL|ATL|PHX|DEN|BOS|"
    r"CALIFORNIA|TEXAS|NEW[ _-]?YORK|FLORIDA|VIRGINIA|VERMONT|"
    r"OREGON|OHIO|NEVADA)",
    re.IGNORECASE)
NEG_MARKERS = re.compile(
    r"(🇮🇷|🇩🇪|🇫🇷|🇳🇱|🇬🇧|🇹🇷|🇷🇺|🇨🇳|🇭🇰|🇸🇬|🇯🇵|🇰🇷|🇮🇳|"
    r"\bDE[-_ ]|\bFR[-_ ]|\bNL[-_ ]|\bUK[-_ ]|\bTR[-_ ]|\bRU[-_ ]|"
    r"\bIR[-_ ]|\bIRAN|GERMANY|FRANCE|NETHERLAND|TURKEY|RUSSIA|IRAN)",
    re.IGNORECASE)

# ── Parsers ───────────────────────────────────────────────────────────────

def parse_vless(line: str) -> Optional[dict]:
    """vless://uuid@host:port?query#remark"""
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
            "net": params.get("type", "tcp"),
            "tls": params.get("security", "none"),
            "sni": params.get("sni", ""),
            "host": params.get("host", ""),
            "path": urllib.parse.unquote(params.get("path", "")),
            "ps": fragment,
            "raw": line,
        }
    except Exception as e:
        log.debug(f"vless parse fail: {e} | {line[:80]}")
        return None


def parse_vmess(line: str) -> Optional[dict]:
    """Only base64-JSON form matters for US filter; URI form is legacy."""
    try:
        payload = line[8:]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload).decode("utf-8")
            cfg = json.loads(decoded)
        except Exception:
            return None
        if not cfg.get("add") or not cfg.get("port"):
            return None
        return {
            "proto": "vmess",
            "id": cfg.get("id"),
            "add": cfg.get("add"),
            "port": int(cfg.get("port")),
            "net": cfg.get("net", "tcp"),
            "tls": cfg.get("tls", ""),
            "sni": cfg.get("sni", ""),
            "host": cfg.get("host", ""),
            "path": cfg.get("path", ""),
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


# ── Source fetch ──────────────────────────────────────────────────────────

def fetch_source(url: str) -> list[str]:
    try:
        r = requests.get(url, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        text = r.text
        if "://" not in text[:200]:
            try:
                text = base64.b64decode(text).decode("utf-8")
            except Exception:
                pass
        return [ln.strip() for ln in text.splitlines()
                if ln.strip().startswith(("vless://", "vmess://"))]
    except Exception as e:
        log.error(f"fetch {url}: {e}")
        return []


# ── Geo resolution ────────────────────────────────────────────────────────

def resolve_host(host: str) -> Optional[str]:
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return None


def batch_geo(ips: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(ips), GEO_BATCH):
        batch = ips[i:i + GEO_BATCH]
        for attempt in range(3):
            try:
                r = requests.post(
                    "http://ip-api.com/batch?fields=countryCode,query",
                    json=batch, timeout=20,
                    headers={"Content-Type": "application/json"})
                if r.status_code == 429:
                    log.warning("ip-api rate limit, sleeping")
                    import time; time.sleep(5)
                    continue
                r.raise_for_status()
                for item in r.json():
                    out[item["query"]] = item.get("countryCode", "").upper()
                break
            except Exception as e:
                log.warning(f"geo batch {i//GEO_BATCH} attempt {attempt}: {e}")
                import time; time.sleep(2)
    return out


# ── Liveness check (TCP only — fast) ──────────────────────────────────────

def tcp_alive(host: str, port: int, timeout: float = TCP_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> Optional[str]:
    raw_lines = []
    for url in SOURCES:
        raw_lines.extend(fetch_source(url))
    log.info(f"Total raw lines: {len(raw_lines)}")

    parsed = [c for c in (parse_line(l) for l in raw_lines) if c]
    log.info(f"Parsed: {len(parsed)}")

    # dedup by (proto, id, host, port)
    seen = OrderedDict()
    for c in parsed:
        key = (c["proto"], c["id"], c["add"], c["port"])
        seen.setdefault(key, c)
    configs = list(seen.values())
    log.info(f"Unique: {len(configs)}")

    # ── Stage 1: remark-based US ─────────────────────────────────────────
    by_remark = []
    candidates = []
    for c in configs:
        text = f"{c.get('ps','')} {c.get('add','')}"
        if US_MARKERS.search(text) and not NEG_MARKERS.search(text):
            by_remark.append(c)
        else:
            candidates.append(c)
    log.info(f"US by remark: {len(by_remark)} | geo candidates: {len(candidates)}")

    # ── Stage 2: geo for non-remark candidates ───────────────────────────
    # Resolve hosts in parallel
    hosts = list({c["add"] for c in candidates})
    host_ip: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(resolve_host, h): h for h in hosts}
        for f in as_completed(futs):
            h = futs[f]
            ip = f.result()
            if ip:
                host_ip[h] = ip

    # Collect IPs that aren't Cloudflare lies
    ips_to_check = []
    cfg_to_ip = {}
    for c in candidates:
        ip = host_ip.get(c["add"])
        if ip and not is_cloudflare(ip):
            cfg_to_ip[id(c)] = ip
            ips_to_check.append(ip)

    uniq_ips = list(set(ips_to_check))
    log.info(f"Geo-checking {len(uniq_ips)} non-CF IPs")
    geo = batch_geo(uniq_ips)

    by_geo = [c for c in candidates
              if cfg_to_ip.get(id(c)) and geo.get(cfg_to_ip[id(c)]) == "US"]
    log.info(f"US by geo: {len(by_geo)}")

    # ── Stage 3: combine, prioritize, liveness ───────────────────────────
    combined = list(OrderedDict.fromkeys(
        c["raw"] for c in (by_remark + by_geo)))
    log.info(f"Combined candidates: {len(combined)}")

    # Reconstruct cfg lookup for liveness test
    raw_to_cfg = {c["raw"]: c for c in (by_remark + by_geo)}

    def check(raw):
        c = raw_to_cfg[raw]
        return raw, tcp_alive(c["add"], c["port"])

    alive = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for raw, ok in ex.map(check, combined):
            if ok:
                alive.append(raw)
    log.info(f"Alive after TCP check: {len(alive)}")

    # Fall back to non-alive if we don't have enough
    final_src = alive if len(alive) >= MAX_RESULTS else combined
    final = final_src[:MAX_RESULTS]

    if not final:
        return ""
    out = "\n".join(final) + "\n"
    return base64.b64encode(out.encode()).decode()


if __name__ == "__main__":
    try:
        r = main()
        if r is None:
            log.error("filter returned None")
        else:
            with open(OUTPUT_FILE, "w") as f:
                f.write(r)
            log.info(f"Wrote {OUTPUT_FILE} ({len(r)} b64 chars)")
    except Exception as e:
        log.exception(f"fatal: {e}")
