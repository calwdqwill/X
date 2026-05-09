@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === TEST PUBLISH (dry-run, no real tweets) ===
python main.py --publish-draft drafts/latest.json --dry-run
echo.
echo === Done! Nothing was actually posted. ===
pause
