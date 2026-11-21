@echo off
rem Double-click: pulls segment data for the companies exported from Plumb.
cd /d "%~dp0"
python -m pip install -q -U -r requirements.txt
python nse_segments.py %*
echo.
pause
