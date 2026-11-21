"""
NSE price history for Plumb
---------------------------
Downloads daily prices (open, high, low, close, volume) for the companies exported from Plumb and writes
plumb-prices.json. In Plumb, drop that file anywhere (or use Import on the Segments page / Upload) and every
company's price history is updated at once, which feeds the Technicals and SOIC pages.

Typical use (on your own PC; NSE blocks cloud servers):
    1. Plumb -> Companies -> tick companies -> "Export selected for scripts"   (plumb-companies.json)
    2. python nse_prices.py            # or double-click run_prices.bat
    3. Drop plumb-prices.json onto Plumb

Options:
    --years 3              how much history on the first run (later runs only fetch new days)
    --symbols NH,FORTIS    ad hoc, without a Plumb export
    --full                 ignore the cache and download everything again

Prices come from NSE through the open-source nselib library (pip install nselib). They are as traded:
not adjusted for splits or bonuses, so a split shows up as a sudden drop. The script warns when it sees one.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import plumb_nse_common as common
from plumb_nse_common import NSE, HERE, load_companies, resolve_symbols

try:
    from nselib import capital_market
except ImportError:  # pragma: no cover
    capital_market = None

CHUNK_DAYS = 365  # NSE serves at most about a year per request


def _norm(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _date(v):
    if isinstance(v, (date, datetime)):
        return v if isinstance(v, date) and not isinstance(v, datetime) else v.date()
    s = str(v).strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def rows_from_table(records: list[dict]) -> dict[date, list]:
    """Pick date/OHLCV columns by name (NSE renames them now and then); keep the EQ series where present."""
    if not records:
        return {}
    cols = {_norm(k): k for k in records[0].keys()}

    def col(exact, contains=None, avoid=None):
        for e in exact:
            if e in cols:
                return cols[e]
        if contains:
            for n, k in cols.items():
                if contains in n and not (avoid and re.search(avoid, n)):
                    return k
        return None

    c = {"d": col(["date", "timestamp", "tradedate", "chdate"], "date"),
         "o": col(["openprice", "open", "chopeningprice"], "open"),
         "h": col(["highprice", "high", "chtradehighprice"], "high", "52"),
         "l": col(["lowprice", "low", "chtradelowprice"], "low", "52"),
         "c": col(["closeprice", "close", "chclosingprice"], "close", "prev|adj"),
         "v": col(["totaltradedquantity", "volume", "chtotaltradedqty", "tottrdqty"], "quantity", "deliver"),
         "s": col(["series", "chseries"])}
    if not c["d"] or not c["c"]:
        raise RuntimeError(f"price table has no date/close columns: {list(records[0].keys())}")
    series = {str(r.get(c["s"], "")).strip().upper() for r in records} if c["s"] else set()
    keep = "EQ" if "EQ" in series else None
    out = {}
    for r in records:
        if keep and str(r.get(c["s"], "")).strip().upper() != keep:
            continue
        d, close = _date(r.get(c["d"])), _num(r.get(c["c"]))
        if not d or not close:
            continue
        g = lambda k: _num(r.get(c[k])) if c[k] else None
        out[d] = [g("o") or close, g("h") or close, g("l") or close, close, g("v")]
    return out


def fetch_range(symbol: str, start: date, end: date, delay: float) -> dict[date, list]:
    if capital_market is None:
        raise RuntimeError("the 'nselib' package is missing: pip install -r requirements.txt")
    out, a = {}, start
    while a <= end:
        b = min(end, a + timedelta(days=CHUNK_DAYS - 1))
        last = None
        for attempt in range(3):
            try:
                df = capital_market.price_volume_data(symbol=symbol, from_date=a.strftime("%d-%m-%Y"), to_date=b.strftime("%d-%m-%Y"))
                recs = df.to_dict("records") if hasattr(df, "to_dict") else list(df or [])
                out.update(rows_from_table(recs))
                last = None
                break
            except Exception as e:  # nselib raises plain exceptions for empty ranges and network trouble
                last = e
                if "no data" in str(e).lower() or "empty" in str(e).lower():
                    last = None
                    break
                time.sleep(2 * (attempt + 1))
        if last:
            raise RuntimeError(f"{symbol} {a}..{b}: {last}")
        time.sleep(delay)
        a = b + timedelta(days=1)
    return out


def cache_file(symbol: str) -> Path:
    return common.CACHE / "prices" / f"{re.sub(r'[^A-Z0-9&-]', '_', symbol)}.csv"


def read_cache(symbol: str) -> dict[date, list]:
    f = cache_file(symbol)
    if not f.exists():
        return {}
    out = {}
    with f.open(newline="", encoding="utf-8") as fh:
        for r in csv.reader(fh):
            if len(r) >= 6 and r[0][:1].isdigit():
                out[date.fromisoformat(r[0])] = [_num(x) for x in r[1:6]]
    return out


def write_cache(symbol: str, rows: dict[date, list]):
    f = cache_file(symbol)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        for d in sorted(rows):
            w.writerow([d.isoformat(), *rows[d]])


def split_warnings(rows: dict[date, list]) -> list[str]:
    """Flag overnight drops that look like splits or bonuses (prices here are not adjusted)."""
    ds, out = sorted(rows), []
    for p, d in zip(ds, ds[1:]):
        prev, cur = rows[p][3], rows[d][0] or rows[d][3]
        if prev and cur and cur / prev < 0.55:
            out.append(f"{d}: price fell from {prev:,.0f} to {cur:,.0f} overnight; probably a split or bonus "
                       f"(prices are not adjusted, so treat technicals across that date with care)")
    return out


def run_company(c: dict, years: float, full: bool, delay: float) -> dict:
    today = date.today()
    first = today - timedelta(days=int(365.25 * years))
    have = {} if full else read_cache(c["symbol"])
    have = {d: v for d, v in have.items() if d >= first} if have else {}
    start = (max(have) + timedelta(days=1)) if have and min(have) <= first + timedelta(days=7) else first
    new = fetch_range(c["symbol"], start, today, delay) if start <= today else {}
    rows = {**have, **new}
    write_cache(c["symbol"], rows)
    return {"name": c["name"], "symbol": c["symbol"],
            "rows": [[d.isoformat(), *[None if v is None else round(v, 4) for v in rows[d]]] for d in sorted(rows)],
            "first": min(rows).isoformat() if rows else None, "last": max(rows).isoformat() if rows else None,
            "new_days": len(new), "warnings": split_warnings(rows)}


def main():
    ap = argparse.ArgumentParser(description="Download daily NSE prices for the companies exported from Plumb.")
    ap.add_argument("--companies", help="plumb-companies.json (default: newest one here or in Downloads)")
    ap.add_argument("--symbols", help="comma-separated NSE symbols instead of a Plumb export")
    ap.add_argument("--years", type=float, default=3, help="years of history to keep (default 3)")
    ap.add_argument("--full", action="store_true", help="ignore the cache and download everything again")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between NSE requests")
    ap.add_argument("--out", default=str(HERE / "plumb-prices.json"), help="output file")
    a = ap.parse_args()
    if capital_market is None:
        sys.exit("This script needs the 'nselib' package:  pip install -r requirements.txt")

    companies = resolve_symbols(load_companies(a), NSE(delay=a.delay))
    results = []
    for i, c in enumerate(companies, 1):
        if not c["symbol"]:
            results.append({"name": c["name"], "symbol": "", "rows": [], "warnings": ["No NSE symbol."]})
            continue
        print(f"[{i}/{len(companies)}] {c['symbol']:<12} {c['name']}")
        try:
            r = run_company(c, a.years, a.full, a.delay)
            print(f"      {len(r['rows'])} days, {r['first']} to {r['last']} ({r['new_days']} new)")
        except RuntimeError as e:
            r = {"name": c["name"], "symbol": c["symbol"], "rows": [], "warnings": [str(e)]}
            print(f"      could not download: {e}")
        for w in r["warnings"][:3]:
            print(f"      note: {w}")
        results.append(r)
    payload = {"kind": "plumb-prices", "version": 1, "generated": datetime.now().isoformat(timespec="seconds"),
               "source": "NSE daily prices via nselib (not split-adjusted)", "companies": results}
    Path(a.out).write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {a.out}. Drop it onto Plumb to update every company's price history.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
