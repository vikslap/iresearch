@echo off
rem Double-click: downloads daily prices for the companies exported from Plumb.
cd /d "%~dp0"
python -m pip install -q -U -r requirements.txt
python nse_prices.py %*
echo.
pause
