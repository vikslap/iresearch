# Plumb NSE tools

Two scripts that fill Plumb with data from NSE for the companies you choose. Both read the same company list exported from Plumb.

| Script | What it gets | Plumb pages it feeds |
|---|---|---|
| `nse_segments.py` | Segment revenue, profit, assets and liabilities from each quarterly results filing | Segments |
| `nse_prices.py` | Daily prices (open, high, low, close, volume) | Technicals, Plumb Score |

## Each time
1. **Plumb → Companies.** Tick the companies you want (or none for all), then click **Export … for scripts**. This saves `plumb-companies.json` to Downloads.
2. **Double-click one of:**
   - `run_all.bat`: segments and prices
   - `run_segments.bat`: segments only
   - `run_prices.bat`: prices only
3. **Drop the output file(s) onto Plumb:** `plumb-segments.json` and/or `plumb-prices.json`, from this folder. Every company in the file is updated at once.

Both scripts keep what they've downloaded in `cache\`, so later runs only fetch what's new: new filings, or the days since the last run.

## Prices
- The first run downloads 3 years per company (`--years 5` for more). After that, only new days are fetched.
- Prices are as traded, **not adjusted for splits or bonuses**. When the script sees an overnight drop that looks like a split, it prints a note, and Plumb shows it. Technical readings across that date will be off.
- Source: NSE's daily price data, via the open-source `nselib` library.

## Symbols
Both scripts match Plumb's company names to NSE symbols, using NSE's list of listed companies:
- exact matches are used directly;
- near matches are marked `?` (check them in `symbols.json`);
- anything not found is marked `!`.

Symbols typed in Plumb's Companies page always win. BSE-only companies aren't covered.

## Options
- `--symbols NH,APOLLOHOSP`: run without a Plumb export.
- `--refresh` (segments) / `--full` (prices): ignore what's cached and check again.
- `--delay 2`: wait longer between requests if NSE starts refusing them.
- `--probe cache\xbrl\<file>.xml` (segments): show every segment item in one filing.

## Notes
- Run on your own PC. NSE blocks requests from cloud servers.
- Requires Python 3.9+. The .bat files install `requests` and `nselib` (`pip install -r requirements.txt`) and keep them updated, which matters because NSE changes its site now and then.
- Shared pieces (NSE connection, company list, symbol matching) live in `plumb_nse_common.py`, so new data types can be added as another small script.
