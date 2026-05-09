@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Cleaning database ===
python clean_db.py
echo.
echo === Done! Database is empty. ===
pause
