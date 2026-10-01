@echo off
cd /d "%~dp0"
"%~dp0python\python.exe" -B -X utf8 export_capture.py
echo.
echo Press any key to close this window.
pause >nul
