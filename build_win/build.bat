@echo off
chcp 65001 > nul
echo ========================================
echo  StockTrader -- PyInstaller Build (PyQt6)
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Install PyQt6 + PyInstaller
echo [1/4] Installing PyQt6 and PyInstaller...
pip install "PyQt6>=6.4.0" "pyinstaller>=6.0.0" --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Install Fubon Neo SDK (Windows wheel)
set FUBON_WHL=..\fubon_neo-2.2.8-cp37-abi3-win_amd64.whl
if exist "%FUBON_WHL%" (
    echo [2/4] Installing fubon_neo SDK from %FUBON_WHL% ...
    pip install "%FUBON_WHL%" --quiet
    if errorlevel 1 (
        echo [ERROR] fubon_neo install failed. Check the .whl path.
        pause
        exit /b 1
    )
) else (
    echo [ERROR] Cannot find %FUBON_WHL%
    echo         Place fubon_neo-2.2.8-cp37-abi3-win_amd64.whl in the parent folder and retry.
    pause
    exit /b 1
)

:: Clean old build/dist
echo [3/4] Cleaning old output folders...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

:: Add Windows Defender exclusions to avoid WinError 225
echo [*] Adding Windows Defender exclusions (requires Administrator)...
set BUILD_DIR=%CD%
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-MpPreference -ExclusionPath '%BUILD_DIR%\build','%BUILD_DIR%\dist' -ErrorAction SilentlyContinue; Write-Host '[*] Defender exclusions added.'"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-MpPreference -ExclusionProcess 'pyinstaller.exe','python.exe' -ErrorAction SilentlyContinue"

:: Run PyInstaller
echo [4/4] Building EXE (1~3 min)...
pyinstaller build.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    echo.
    echo If WinError 225 still occurs:
    echo   1. Right-click build.bat -^> Run as Administrator
    echo   2. Or manually add exclusion folders in Windows Security:
    echo      %BUILD_DIR%\build
    echo      %BUILD_DIR%\dist
    pause
    exit /b 1
)

:: Remove Defender exclusions (cleanup)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-MpPreference -ExclusionProcess 'pyinstaller.exe','python.exe' -ErrorAction SilentlyContinue"

:: Rename output EXE
if exist dist\StockTrader.exe (
    copy dist\StockTrader.exe "dist\StockTrader-final.exe" >nul
    del dist\StockTrader.exe
)

echo.
echo ========================================
echo  Build complete!
echo  Output: dist\StockTrader-final.exe
echo ========================================
echo.
explorer dist
pause
