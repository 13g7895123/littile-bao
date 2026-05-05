@echo off
chcp 65001 > nul
echo ========================================
echo  台股漲停交易系統 — PyInstaller 打包（PyQt6 版）
echo ========================================
echo.

:: 確認 Python 可用
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10+
    pause
    exit /b 1
)

:: 安裝依賴
echo [1/3] 安裝 PyQt6、PyInstaller 和富邦 SDK...
pip install "PyQt6>=6.4.0" "pyinstaller>=6.0.0" --quiet
if errorlevel 1 (
    echo [錯誤] 安裝依賴失敗
    pause
    exit /b 1
)

:: 安裝富邦 SDK（Windows 版 .whl）
set FUBON_WHL=..\fubon_neo-2.2.8-cp37-abi3-win_amd64.whl
if exist "%FUBON_WHL%" (
    echo [1/3] 安裝富邦 fubon_neo SDK ^(%FUBON_WHL%^)...
    pip install "%FUBON_WHL%" --quiet
    if errorlevel 1 (
        echo [錯誤] 富邦 SDK 安裝失敗，請確認 .whl 路徑正確
        pause
        exit /b 1
    )
) else (
    echo [警告] 找不到 %FUBON_WHL%
    echo         請將 fubon_neo-2.2.8-cp37-abi3-win_amd64.whl 放在上層目錄後重試
    pause
    exit /b 1
)

:: 清理舊的 build/dist
echo [2/3] 清理舊的輸出目錄...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

:: 執行打包
echo [3/3] 開始打包（這需要 1~3 分鐘）...
pyinstaller build.spec

if errorlevel 1 (
    echo.
    echo [錯誤] 打包失敗，請查看上方訊息
    pause
    exit /b 1
)

:: 重命名 exe
if exist dist\StockTrader.exe (
    copy dist\StockTrader.exe "dist\台股漲停交易系統.exe" >nul
    del dist\StockTrader.exe
)

echo.
echo ========================================
echo  打包完成！
echo  執行檔位置：dist\台股漲停交易系統.exe
echo ========================================
echo.
explorer dist
pause
