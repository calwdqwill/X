@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo  WARNING: LIVE POSTING to @0x_cryptodex
echo ========================================
echo.
echo This will publish real tweets from:
echo   drafts\latest.json
echo.
set /p confirm="Are you sure? (yes/no): "
if /i not "%confirm%"=="yes" (
    echo Cancelled.
    pause
    exit /b
)
echo.
echo === Publishing... ===
python main.py --publish-draft drafts/latest.json
echo.
echo === Done! ===
pause
