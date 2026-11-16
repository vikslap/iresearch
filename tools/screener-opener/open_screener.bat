@echo off
rem Double-click to open your shortlist on Screener one company at a time.
cd /d "%~dp0"
python screener_open.py %*
echo.
pause
