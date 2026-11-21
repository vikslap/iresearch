"""
Shared pieces for the Plumb NSE tools: a polite NSE client, reading the company list exported from
Plumb, and matching company names to NSE symbols. Used by nse_segments.py and nse_prices.py.
"""
from __future__ import annotations

import csv
import difflib
import io
import json
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("These tools need the 'requests' package:  pip install -r requirements.txt")

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
SYMBOLS_FILE = HERE / "symbols.json"

# NSE has been redirecting .com to .in; both are tried.
SITE_HOSTS = ["https://www.nseindia.com", "https://www.nseindia.in"]
ARCHIVE_HOSTS = ["https://nsearchives.nseindia.com", "https://nsearchives.nseindia.in"]


# ----------------------------------------------------------------------------------------------
# NSE client: browser-like session, warm-up for cookies, throttling, retries
# ----------------------------------------------------------------------------------------------
class NSE:
    def __init__(self, delay: float = 1.2, timeout: int = 45):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.delay, self.timeout, self._last = delay, timeout, 0.0
        self.site = SITE_HOSTS[0]
        self.warmed = False

    def _wait(self):
        gap = time.time() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.time()

    def warm(self):
        """Visit the results page once so NSE sets its cookies; remember which host answered."""
        for host in SITE_HOSTS:
            try:
                self._wait()
                r = self.s.get(f"{host}/companies-listing/corporate-filings-financial-results",
                               timeout=self.timeout, headers={"Accept": "text/html,*/*"})
                if r.ok:
                    m = re.match(r"https?://[^/]+", r.url)
                    self.site = m.group(0) if m else host
                    self.warmed = True
                    return
            except requests.RequestException:
                continue
        self.warmed = True  # carry on; the API call will report the problem

    def get(self, url: str, params: dict | None = None, accept_json: bool = False):
        if not self.warmed:
            self.warm()
        last = None
        for attempt in range(4):
            try:
                self._wait()
                r = self.s.get(url, params=params, timeout=self.timeout,
                               headers={"Referer": f"{self.site}/companies-listing/corporate-filings-financial-results"})
                if r.status_code in (401, 403):
                    self.warm()
                    raise requests.HTTPError(f"{r.status_code} from NSE")
                r.raise_for_status()
                return r.json() if accept_json else r.content
            except (requests.RequestException, ValueError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"NSE request failed after retries: {url} ({last})")


# ----------------------------------------------------------------------------------------------
# Companies and symbols
# ----------------------------------------------------------------------------------------------
def find_companies_file(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    cands = list(HERE.glob("plumb-companies*.json")) + list((Path.home() / "Downloads").glob("plumb-companies*.json"))
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def load_companies(args) -> list[dict]:
    if args.symbols:
        return [{"name": s.strip().upper(), "symbol": s.strip().upper()} for s in args.symbols.split(",") if s.strip()]
    f = find_companies_file(args.companies)
    if not f or not f.exists():
        sys.exit("No company list found. In Plumb: Companies page -> 'Export list for scripts', "
                 "or pass --symbols NH,APOLLOHOSP")
    data = json.loads(f.read_text(encoding="utf-8"))
    rows = data.get("companies", data) if isinstance(data, dict) else data
    print(f"Companies from {f} ({len(rows)})")
    return [{"name": r["name"], "symbol": (r.get("symbol") or "").strip().upper()} for r in rows if r.get("name")]


def norm_name(n: str) -> str:
    n = re.sub(r"['\u2019`]", "", n.upper()).replace("&", " AND ")
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    n = re.sub(r"\bLIMITED\b", "LTD", n)
    n = re.sub(r"^THE\s+", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return re.sub(r"\s+LTD$", "", n)


def equity_list(nse: NSE) -> dict[str, str]:
    """NSE's list of listed equities: normalised company name -> symbol. Cached for a week."""
    f = CACHE / "EQUITY_L.csv"
    if not f.exists() or time.time() - f.stat().st_mtime > 7 * 86400:
        for host in ARCHIVE_HOSTS:
            try:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(nse.get(f"{host}/content/equities/EQUITY_L.csv"))
                break
            except RuntimeError:
                continue
    if not f.exists():
        return {}
    out = {}
    for row in csv.DictReader(io.StringIO(f.read_text(encoding="utf-8", errors="ignore"))):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if row.get("SYMBOL") and row.get("NAME OF COMPANY"):
            out[norm_name(row["NAME OF COMPANY"])] = row["SYMBOL"]
    return out


def resolve_symbols(companies: list[dict], nse: NSE) -> list[dict]:
    saved = json.loads(SYMBOLS_FILE.read_text(encoding="utf-8")) if SYMBOLS_FILE.exists() else {}
    table = None
    for c in companies:
        if c["symbol"]:
            continue
        if c["name"] in saved and saved[c["name"]].get("symbol") and "please confirm" not in saved[c["name"]].get("how", ""):
            c["symbol"] = saved[c["name"]]["symbol"]
            continue
        table = table if table is not None else equity_list(nse)
        key = norm_name(c["name"])
        if key in table:
            c["symbol"] = table[key]
            saved[c["name"]] = {"symbol": c["symbol"], "how": "exact name match"}
            continue
        first = key.split(" ")[0]
        guess = [g for g in difflib.get_close_matches(key, list(table), n=3, cutoff=0.82) if g.split(" ")[0] == first][:1]
        if guess:
            c["symbol"] = table[guess[0]]
            saved[c["name"]] = {"symbol": c["symbol"], "how": f"closest name: {guess[0]} - please confirm (change this text to keep it)"}
            print(f"  ? {c['name']} -> {c['symbol']} (closest name match; check symbols.json)")
        else:
            saved[c["name"]] = {"symbol": "", "how": "not found - type the NSE symbol here"}
            print(f"  ! {c['name']}: not found on NSE (BSE-only companies are not covered). If it is on NSE, type its symbol in Plumb.")
    SYMBOLS_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
    return companies
