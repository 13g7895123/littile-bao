@echo off
chcp 65001 > nul
echo ========================================
echo  台股漲停交易系統 — PyInstaller 打包
echo ========================================
echo.

:: 確認 Python 可用
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10+
    pause
    exit /b 1
)

:: 安裝 PyInstaller
echo [1/3] 安裝 PyInstaller...
pip install pyinstaller>=6.0.0 --quiet
if errorlevel 1 (
    echo [錯誤] 安裝 pyinstaller 失敗
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

echo.
echo ========================================
echo  打包完成！
echo  執行檔位置：dist\台股漲停交易系統.exe
echo ========================================
echo.
explorer dist
pause
