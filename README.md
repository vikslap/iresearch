# Stock Fundamentals Dashboard

A single-page dashboard for Indian stocks built on [screener.in](https://www.screener.in) Excel exports.

## What it does

- **Upload** any screener.in "Export to Excel" file (it reads the *Data Sheet* tab).
- **Overview, Quarterly, Ratios, Valuation** – 10-year financials, ~35 ratios in collapsible groups, P/E / EV-EBITDA / P/B history and a DCF with reverse-DCF.
- **SOIC score** – the 30-question SOIC ranking sheet (out of 310). Fundamentals answer themselves from the data; technicals answer themselves from a price CSV (NSE, BSE, Investing.com, TradingView, AmiBroker or Yahoo).
- **Compare** – rank up to 6 saved companies side by side.
- **Edit data** – change any number; everything recalculates. Download the edited workbook.
- Every chart can be copied as an image or as Excel-ready data.
- Light / dark / system theme.

Everything runs in the browser. Uploaded files, edits, answers and prices are stored only in your browser's local storage – nothing is sent to a server.

## Run locally

Open `index.html` in a browser. No build step.

## Data

The bundled sample (Cenlub Industries) is from a screener.in export and is included for demonstration only.
