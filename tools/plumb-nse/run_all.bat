@echo off
rem Double-click: segments and prices for the companies exported from Plumb.
cd /d "%~dp0"
python -m pip install -q -U -r requirements.txt
python nse_segments.py
echo.
python nse_prices.py
echo.
echo Drop plumb-segments.json and plumb-prices.json onto Plumb.
pause
