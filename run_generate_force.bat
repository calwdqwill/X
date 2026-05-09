@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Force generate (all tweets, ignoring cache) ===
python main.py --generate-only --dry-run --fetch-all
echo.
echo === Done! Check drafts/latest.json ===
pause
