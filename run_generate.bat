@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Generating drafts ===
python main.py --generate-only --dry-run
echo.
echo === Done! Check drafts/latest.json ===
pause
