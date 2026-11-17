"""
NSE segment extractor for Plumb
-------------------------------
Pulls segment-wise revenue, results (profit before interest and tax), assets and liabilities for the
companies in Plumb from the quarterly results that companies file with NSE ("Integrated Filing -
Financials", machine-readable XBRL). Writes plumb-segments.json, which Plumb's Segments tab imports.

Typical use (run on your own PC; NSE blocks cloud servers):
    1. In Plumb, Companies page -> "Export list for scripts"  (saves plumb-companies.json)
    2. python nse_segments.py                 # finds plumb-companies.json here or in Downloads
    3. In Plumb, Segments tab -> Import, choose plumb-segments.json

Other ways to run:
    python nse_segments.py --symbols NH,APOLLOHOSP      # ad hoc, without Plumb
    python nse_segments.py --probe some_filing.xml      # show every segment fact in one XBRL file
    python nse_segments.py --refresh                    # re-check NSE for new filings now

Design notes (for adding more later):
    * Each stage is its own function: companies -> symbols -> filings -> XBRL -> segments -> output.
    * Everything fetched is cached under ./cache, so re-runs only download new filings.
    * Symbols that could not be matched exactly are written to symbols.json for you to confirm or fix;
      that file is read first on every run.
Requires: Python 3.9+, `pip install requests`
"""
from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("This script needs the 'requests' package:  pip install requests")

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
SYMBOLS_FILE = HERE / "symbols.json"
CRORE = 1e7

# Filing list and archive hosts. NSE has been redirecting .com to .in; both are tried.
SITE_HOSTS = ["https://www.nseindia.com", "https://www.nseindia.in"]
ARCHIVE_HOSTS = ["https://nsearchives.nseindia.com", "https://nsearchives.nseindia.in"]
FILING_TYPE = "Integrated Filing- Financials"  # exact spelling NSE expects

# XBRL tags for the SEBI segment table (in-capmkt taxonomy)
SEG_NAME = "DescriptionOfReportableSegment"
SEG_MEASURES = {
    "SegmentRevenue": "revenue",
    "SegmentProfitLossBeforeTaxAndFinanceCosts": "result",
    "SegmentAssets": "assets",
    "SegmentLiabilities": "liabilities",
}
SEG_MEMBER = re.compile(r"ReportableSegments?(\d+)Member$")
NS_XBRLI = "{http://www.xbrl.org/2003/instance}"
NS_DIM = "{http://xbrl.org/2006/xbrldi}"


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
    n = n.upper().replace("&", " AND ")
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
        if c["name"] in saved and saved[c["name"]].get("symbol"):
            c["symbol"] = saved[c["name"]]["symbol"]
            continue
        table = table if table is not None else equity_list(nse)
        key = norm_name(c["name"])
        if key in table:
            c["symbol"] = table[key]
            saved[c["name"]] = {"symbol": c["symbol"], "how": "exact name match"}
            continue
        guess = difflib.get_close_matches(key, list(table), n=1, cutoff=0.82)
        if guess:
            c["symbol"] = table[guess[0]]
            saved[c["name"]] = {"symbol": c["symbol"], "how": f"closest name: {guess[0]} - please confirm"}
            print(f"  ? {c['name']} -> {c['symbol']} (closest name match; check symbols.json)")
        else:
            saved[c["name"]] = {"symbol": "", "how": "not found - type the NSE symbol here"}
            print(f"  ! {c['name']}: no NSE symbol found. Add it in Plumb or in symbols.json")
    SYMBOLS_FILE.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
    return companies


# ----------------------------------------------------------------------------------------------
# Filings
# ----------------------------------------------------------------------------------------------
def list_filings(nse: NSE, symbol: str, refresh: bool) -> list[dict]:
    f = CACHE / "lists" / f"{symbol}.json"
    if f.exists() and not refresh and time.time() - f.stat().st_mtime < 86400:
        return json.loads(f.read_text(encoding="utf-8"))
    rows, page = [], 1
    while True:
        data = nse.get(f"{nse.site}/api/integrated-filing-results", accept_json=True, params={
            "index": "equities", "type": FILING_TYPE, "symbol": symbol, "page": page, "size": 100})
        batch = data.get("data") if isinstance(data, dict) else None
        if not isinstance(batch, list) or not batch:
            break
        rows += batch
        total = int(data.get("totalCount") or 0) if isinstance(data, dict) else 0
        if len(rows) >= total or len(batch) < 100:
            break
        page += 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def pick_filings(rows: list[dict]) -> list[dict]:
    """One filing per quarter end: consolidated if filed, latest revision wins."""
    def qe(r):
        try:
            return datetime.strptime(r.get("qe_Date", ""), "%d-%b-%Y").date()
        except ValueError:
            return None
    best = {}
    for r in rows:
        d, link = qe(r), r.get("xbrl")
        if not d or not link or not str(link).lower().endswith(".xml"):
            continue
        cons = str(r.get("consolidated", "")).lower().startswith("consol")
        rank = (cons, str(r.get("type_Sub", "")).lower().startswith("revis"), str(r.get("creation_Date", "")), int(r.get("seq_Id") or 0))
        if d not in best or rank > best[d][0]:
            best[d] = (rank, r)
    return [best[d][1] | {"_qe": d.isoformat()} for d in sorted(best)]


def fetch_xbrl(nse: NSE, link: str) -> bytes:
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", link.rsplit("/", 1)[-1])
    f = CACHE / "xbrl" / name
    if f.exists():
        return f.read_bytes()
    content = None
    for host in [None] + ARCHIVE_HOSTS:  # try the link as given, then the other archive hosts
        url = link if host is None else re.sub(r"^https?://[^/]+", host, link)
        try:
            content = nse.get(url)
            break
        except RuntimeError:
            continue
    if content is None:
        raise RuntimeError(f"could not download {link}")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(content)
    return content


# ----------------------------------------------------------------------------------------------
# XBRL parsing
# ----------------------------------------------------------------------------------------------
def _d(s: str | None):
    try:
        return date.fromisoformat(s.strip()[:10]) if s else None
    except ValueError:
        return None


def parse_xbrl(content: bytes) -> dict:
    """Return contexts and facts from an XBRL instance (only the bits we need)."""
    root = ET.fromstring(content)
    ctx = {}
    for c in root.iter(f"{NS_XBRLI}context"):
        p = c.find(f"{NS_XBRLI}period")
        dims = {m.get("dimension", ""): (m.text or "").strip() for m in c.iter(f"{NS_DIM}explicitMember")}
        ctx[c.get("id")] = {
            "start": _d(p.findtext(f"{NS_XBRLI}startDate")) if p is not None else None,
            "end": _d(p.findtext(f"{NS_XBRLI}endDate") or p.findtext(f"{NS_XBRLI}instant")) if p is not None else None,
            "instant": p is not None and p.find(f"{NS_XBRLI}instant") is not None,
            "dims": dims,
        }
    facts = []
    for el in root:
        ref = el.get("contextRef")
        if not ref or ref not in ctx:
            continue
        facts.append({"name": el.tag.split("}")[-1], "ctx": ref, "value": (el.text or "").strip(), "unit": el.get("unitRef")})
    return {"ctx": ctx, "facts": facts}


def _num(v: str):
    try:
        return float(v.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _kind(c: dict, qe: date):
    """Classify a period: Q (a quarter ending at qe), FY (twelve months ending at qe), or None."""
    if c["end"] != qe:
        return None
    if c["instant"]:
        return "I"
    if not c["start"]:
        return None
    days = (c["end"] - c["start"]).days
    if 80 <= days <= 100:
        return "Q"
    if 350 <= days <= 380:
        return "FY"
    if 170 <= days <= 190:
        return "H"
    return None


def segments_from_xbrl(content: bytes, qe: date) -> dict:
    x = parse_xbrl(content)
    ctx, facts = x["ctx"], x["facts"]
    names, vals, totals, info, other = {}, {}, {}, {}, set()
    for f in facts:
        c = ctx[f["ctx"]]
        seg = None
        for member in c["dims"].values():
            m = SEG_MEMBER.search(member)
            if m:
                seg = int(m.group(1))
        if seg is not None:
            if f["name"] == SEG_NAME:
                if f["value"]:
                    names.setdefault(seg, f["value"])
                continue
            k = _kind(c, qe)
            v = _num(f["value"])
            if k is None or v is None:
                continue
            measure = SEG_MEASURES.get(f["name"])
            if not measure:
                if f["name"].startswith("Segment"):
                    other.add(f["name"])
                continue
            for kk in (["Q", "FY", "H"] if k == "I" else [k]):  # balances apply to every period ending on that date
                vals.setdefault(kk, {}).setdefault(seg, {})[measure] = v / CRORE
        elif not c["dims"]:
            if f["name"] in ("RevenueFromOperations", "SegmentRevenueFromOperations"):
                k, v = _kind(c, qe), _num(f["value"])
                if k in ("Q", "FY", "H") and v is not None:
                    totals.setdefault(k, {})[f["name"]] = v / CRORE
            elif f["name"] in ("NatureOfReportStandaloneConsolidated", "LevelOfRounding") or "SingleSegment" in f["name"] \
                    or f["name"] in ("SegmentReporting", "WhetherCompanyHasSingleOrMultipleSegments"):
                if f["value"]:
                    info.setdefault(f["name"], f["value"])
    periods = []
    for k in ("Q", "H", "FY"):
        if k not in vals or not any("revenue" in s or "result" in s for s in vals[k].values()):
            continue
        segs = [{"name": names.get(n, f"Segment {n}"), **{m: round(v, 2) for m, v in vals[k][n].items()}} for n in sorted(vals[k])]
        tot = totals.get(k, {})
        total = tot.get("SegmentRevenueFromOperations") or tot.get("RevenueFromOperations")
        ssum = sum(s.get("revenue", 0) or 0 for s in segs)
        periods.append({"kind": k, "end": qe.isoformat(), "segments": segs,
                        "revenue_total": round(total, 2) if total else None,
                        "check": {"segment_sum": round(ssum, 2), "total": round(total, 2) if total else None,
                                  "ok": (abs(ssum - total) <= max(1.0, .03 * abs(total))) if total else None}})
    single = None
    if not periods:
        desc = next((v for k, v in info.items() if "SingleSegment" in k and "Description" in k), None)
        flag = next((v for k, v in info.items() if k in ("SegmentReporting", "WhetherCompanyHasSingleOrMultipleSegments")), "")
        if desc or "single" in flag.lower():
            single = desc or "single segment"
    return {"periods": periods, "single": single, "basis": info.get("NatureOfReportStandaloneConsolidated"),
            "unmapped": sorted(other)}


# ----------------------------------------------------------------------------------------------
# Main flow
# ----------------------------------------------------------------------------------------------
def run_company(nse: NSE, c: dict, refresh: bool) -> dict:
    out = {"name": c["name"], "symbol": c["symbol"], "periods": [], "single_segment": None, "warnings": []}
    rows = list_filings(nse, c["symbol"], refresh)
    picks = pick_filings(rows)
    if not picks:
        out["warnings"].append("No integrated results filings found on NSE (check the symbol).")
        return out
    by_key = {}
    for r in picks:
        qe = date.fromisoformat(r["_qe"])
        try:
            res = segments_from_xbrl(fetch_xbrl(nse, r["xbrl"]), qe)
        except (RuntimeError, ET.ParseError) as e:
            out["warnings"].append(f"{r['_qe']}: {e}")
            continue
        if res["single"]:
            out["single_segment"] = res["single"]
        for p in res["periods"]:
            p.update({"basis": res["basis"] or r.get("consolidated"), "filing": r["xbrl"]})
            by_key[(p["kind"], p["end"])] = p  # later filings replace earlier ones for the same period
            if p["check"]["ok"] is False:
                out["warnings"].append(f"{p['kind']} {p['end']}: segment revenues add to {p['check']['segment_sum']} "
                                       f"vs reported {p['check']['total']} crore")
        if res["unmapped"]:
            out["warnings"].append(f"{r['_qe']}: segment items not read yet: {', '.join(res['unmapped'])}")
    out["periods"] = [by_key[k] for k in sorted(by_key, key=lambda k: (k[1], k[0]))]
    out["basis"] = next((p["basis"] for p in reversed(out["periods"]) if p.get("basis")), None)
    return out


def probe(path: str):
    content = Path(path).read_bytes()
    x = parse_xbrl(content)
    print(f"{len(x['ctx'])} contexts, {len(x['facts'])} facts")
    for f in x["facts"]:
        dims = x["ctx"][f["ctx"]]["dims"]
        if any(SEG_MEMBER.search(m) for m in dims.values()) or "Segment" in f["name"]:
            c = x["ctx"][f["ctx"]]
            print(f"{f['name']:<50} {f['ctx']:<26} {c['start']}..{c['end']} {list(dims.values())} = {f['value'][:60]}")


def main():
    ap = argparse.ArgumentParser(description="Extract segment data from NSE quarterly results for Plumb.")
    ap.add_argument("--companies", help="plumb-companies.json exported from Plumb (default: newest one here or in Downloads)")
    ap.add_argument("--symbols", help="comma-separated NSE symbols instead of a Plumb export")
    ap.add_argument("--out", default=str(HERE / "plumb-segments.json"), help="output file")
    ap.add_argument("--refresh", action="store_true", help="re-check NSE for new filings even if checked today")
    ap.add_argument("--delay", type=float, default=1.2, help="seconds between NSE requests (be gentle)")
    ap.add_argument("--probe", help="print every segment fact in one XBRL file and exit")
    a = ap.parse_args()
    if a.probe:
        return probe(a.probe)

    nse = NSE(delay=a.delay)
    companies = resolve_symbols(load_companies(a), nse)
    results = []
    for i, c in enumerate(companies, 1):
        if not c["symbol"]:
            results.append({"name": c["name"], "symbol": "", "periods": [], "warnings": ["No NSE symbol."]})
            continue
        print(f"[{i}/{len(companies)}] {c['symbol']:<12} {c['name']}")
        try:
            r = run_company(nse, c, a.refresh)
        except RuntimeError as e:
            r = {"name": c["name"], "symbol": c["symbol"], "periods": [], "warnings": [str(e)]}
        q = [p for p in r["periods"] if p["kind"] == "Q"]
        note = f"single segment ({r['single_segment']})" if r.get("single_segment") else \
            f"{len(q)} quarters, segments: {', '.join(s['name'] for s in q[-1]['segments'])}" if q else "no segment data"
        print(f"      {note}")
        for w in r["warnings"][:4]:
            print(f"      note: {w}")
        results.append(r)
    payload = {"kind": "plumb-segments", "version": 1, "generated": datetime.now().isoformat(timespec="seconds"),
               "source": "NSE Integrated Filing - Financials (XBRL)", "unit": "INR crore", "companies": results}
    Path(a.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {a.out}. In Plumb: Segments tab -> Import, and choose this file.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
