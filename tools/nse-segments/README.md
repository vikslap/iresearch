# NSE segment extractor

Pulls segment data (revenue, profit before interest and tax, assets, liabilities) for the companies in Plumb from the quarterly results that companies file with NSE. It reads the machine-readable version of the filing (XBRL), so the figures come straight from the company's own submission.

## Each results season
1. **Plumb → Companies → Export list for scripts.** Saves `plumb-companies.json` to your Downloads folder.
2. **Double-click `run_segments.bat`.** It finds the export, looks up each company's NSE symbol, downloads any filings it hasn't seen before, and writes `plumb-segments.json` in this folder.
3. **Plumb → Segments → Import**, and choose `plumb-segments.json`.

The first run downloads every quarter available. Later runs only fetch new filings, since everything is cached in `cache\`.

## Symbols
The script matches Plumb's company names to NSE symbols using NSE's list of listed companies.
- Exact matches are used directly.
- Near matches are used but printed with a `?`. Check them in `symbols.json`.
- Anything it can't match is printed with `!`. Type the symbol in Plumb's Companies page, or in `symbols.json`, and run again.

Symbols you type in Plumb always take priority.

## What you get
- Every quarter since NSE moved to the "Integrated Filing" format (results for quarters ending March 2025 onwards), plus full-year figures from each March quarter.
- Consolidated figures where the company files them, otherwise standalone.
- A check that segment revenues add up to the reported total. Mismatches are printed and shown in Plumb.
- Companies with a single segment are marked as such. There's nothing more to break down.

## Options
- `--symbols NH,APOLLOHOSP`: run for specific symbols without a Plumb export.
- `--refresh`: re-check NSE for new filings even if it already checked today.
- `--delay 2`: wait longer between requests if NSE starts refusing them.
- `--probe cache\xbrl\<file>.xml`: print every segment item in one filing. Useful if a company's segments come out empty or odd.

## Notes
- Run it on your own PC. NSE blocks requests from cloud servers.
- It waits about a second between requests, to stay polite to NSE's site.
- Requires Python 3.9+ and the `requests` package (the .bat installs it).
- Built so more data can be added later (for example shareholding or other filing types): each step (companies, symbols, filings, parsing, output) is a separate function.
