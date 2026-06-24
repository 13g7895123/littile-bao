@echo off
setlocal

cd /d "%~dp0"
echo Running Windows time repair with Administrator elevation...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0repair_windows_time_auto_admin.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Time repair finished.
) else (
    echo Time repair failed with exit code %EXIT_CODE%.
)
echo Summary folder: C:\Jarvis\15_bonus\01_littile-bao
echo.
pause
exit /b %EXIT_CODE%
