@echo off
setlocal

cd /d "%~dp0"
echo Running Windows time guard before launching StockTrader...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_trader_with_time_guard.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Trader launch guard completed.
) else (
    echo Trader launch guard failed with exit code %EXIT_CODE%.
)
echo Summary folder: C:\Jarvis\15_bonus\01_littile-bao
echo.
pause
exit /b %EXIT_CODE%
