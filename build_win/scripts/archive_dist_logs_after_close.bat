@echo off
setlocal

cd /d "%~dp0"

set "SOURCE_DIR=%~dp0..\dist\log"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "RUN_DATE=%%I"
set "TARGET_ROOT=C:\Jarvis\15_bonus\01_littile-bao\log"
set "TARGET_DIR=%TARGET_ROOT%\%RUN_DATE%"

echo Source: %SOURCE_DIR%
echo Target: %TARGET_DIR%
echo.

if not exist "%SOURCE_DIR%\" (
    echo Source log folder does not exist.
    exit /b 1
)

if not exist "%TARGET_ROOT%\" (
    mkdir "%TARGET_ROOT%"
    if errorlevel 1 (
        echo Failed to create target root: %TARGET_ROOT%
        exit /b 1
    )
)

if not exist "%TARGET_DIR%\" (
    mkdir "%TARGET_DIR%"
    if errorlevel 1 (
        echo Failed to create date folder: %TARGET_DIR%
        exit /b 1
    )
)

robocopy "%SOURCE_DIR%" "%TARGET_DIR%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
set "ROBOCOPY_EXIT=%ERRORLEVEL%"

if %ROBOCOPY_EXIT% GEQ 8 (
    echo Log archive failed. robocopy exit code: %ROBOCOPY_EXIT%
    exit /b %ROBOCOPY_EXIT%
)

echo Log archive completed for %RUN_DATE%.
echo Output folder: %TARGET_DIR%
exit /b 0
