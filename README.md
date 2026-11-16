# Plumb

**Get to the bottom of any stock.**

Plumb is a single-page research tool for Indian stocks built on [screener.in](https://www.screener.in) Excel exports.

Live: https://vikslap.github.io/iresearch/

## What it does

- **Upload** any screener.in "Export to Excel" file (it reads the *Data Sheet* tab).
- **Overview, Quarterly, Ratios, Valuation** – 10-year financials, ~35 ratios in collapsible groups, P/E bands, an expected-return calculator and a DCF (free cash flow or net profit) with reverse-DCF.
- **Quality** – automatic red-flag checks, ROE drivers, incremental ROCE, self-funded growth and ten-year sources and uses of cash.
- **SOIC score** – the 30-question SOIC ranking sheet (out of 310). Fundamentals answer themselves from the data; technicals answer themselves from a price CSV (NSE, BSE, Investing.com, TradingView, AmiBroker or Yahoo).
- **Compare** – rank up to 6 saved companies side by side.
- **Results season** – re-upload a fresh export and see what changed (new quarters and years, TTM sales and profit, price, P/E, ROCE, SOIC, red flags, revised past figures); latest-quarter scorecard vs a year ago, last quarter and the four-quarter average.
- **Companies and Sectors** – a sortable, filterable list of saved companies with pins and sector tags (Ctrl + K to jump to one), and a sector view with medians, a rank heatmap, premium/discount to the sector vs each company's usual level, market-share shifts, and a labelled quadrant chart (bubble size = market cap, choice of axes).
- **Scenario valuation** – pessimistic, base and optimistic cases: projected EPS × justified P/E (from long-run growth, sustainable ROE and required return), discounted to today and probability-weighted.
- **Valuation extras** – DCF sensitivity grid (discount rate × growth) and a reverse-DCF slider showing the growth priced in.
- **Install as an app** – add Plumb to your phone's home screen or your computer's app list; it works offline with the data already on the device.
- **Edit data** – change any number; everything recalculates. Download the edited workbook.
- Every chart can be copied as an image or as Excel-ready data.
- **Sync across devices** – link devices with a QR code or sync code; everything is end-to-end encrypted in the browser before it is uploaded (see `sync-worker/`).
- Light / dark / system theme.

Everything runs in the browser. Uploaded files, edits, answers and prices are stored in your browser's local storage. If you turn on sync, they are encrypted with a key derived from your sync code before being sent to your own sync server, which cannot read them.

## Run locally

Open `index.html` in a browser. No build step.

## Data

The bundled sample (Cenlub Industries) is from a screener.in export and is included for demonstration only.
