@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0python\python.exe" -B -X utf8 copy_app_refresh.py
echo.
echo 按任意键关闭窗口。
pause
