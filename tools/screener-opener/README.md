# Screener opener

Opens each company on your shortlist on screener.in, one at a time, in your normal browser. You click **Export to Excel** yourself, then press Enter in the window for the next company. At the end the downloaded files are moved into `exports\<date>\`, ready to upload to Plumb in one go.

Nothing logs in or downloads automatically: it only opens pages, so you use Screener exactly as you would by hand.

## Setup (once)
1. Install Python 3 from python.org (tick "Add Python to PATH").
2. Copy this folder anywhere on your PC.
3. Edit `watchlist.txt`: one NSE symbol per line (the part after `/company/` in a Screener URL). Use the BSE code for BSE-only companies.
4. Make sure you're logged in to Screener in your default browser.

## Each results season
1. Double-click `open_screener.bat`.
2. In each tab, click **Export to Excel**, then press Enter in the black window.
3. When the last download finishes, press Enter once more. The folder with all the files opens.
4. In Plumb, click Upload and select them all.

## Options
- `--batch 5`: open 5 tabs at a time.
- `--list hospitals.txt`: use a different list (keep several lists for different sectors).
- `--standalone`: standalone figures instead of consolidated.
- `--downloads "D:\Downloads"`: if your browser saves somewhere other than Downloads.
- `--no-collect`: leave files in Downloads.

Example: `python screener_open.py --list hospitals.txt --batch 4`
