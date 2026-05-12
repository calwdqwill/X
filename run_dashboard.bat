@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   X Hybrid Poster Dashboard
echo ==========================================
echo.
echo Opening http://127.0.0.1:8080 in your browser...
echo.
start http://127.0.0.1:8080
python app.py
echo.
echo Dashboard stopped.
pause
