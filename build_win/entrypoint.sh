#!/bin/bash
set -e

# 啟動 Xvfb 虛擬 display
Xvfb :0 -screen 0 1024x768x24 -nolisten tcp &
sleep 2
export DISPLAY=:0

WINEPREFIX=/wine
export WINEPREFIX
export WINEARCH=win64

echo "[Wine] 初始化 Wine 環境..."
wine wineboot --init 2>/dev/null || true
wineserver -w 2>/dev/null || true
sleep 3

PYTHON_DIR="C:/Python311"
PYTHON_EXE="$WINEPREFIX/drive_c/Python311/python.exe"

if [ ! -f "$PYTHON_EXE" ]; then
    echo "[Python] 安裝 Python 3.11 embeddable..."
    wget -q https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip \
        -O /tmp/py-embed.zip
    mkdir -p "$WINEPREFIX/drive_c/Python311"
    unzip -q /tmp/py-embed.zip -d "$WINEPREFIX/drive_c/Python311"
    rm /tmp/py-embed.zip
    # 啟用 site-packages
    sed -i 's/^#import site/import site/' "$WINEPREFIX/drive_c/Python311/python311._pth" 2>/dev/null || true

    echo "[pip] 安裝 pip..."
    wget -q https://bootstrap.pypa.io/get-pip.py -O /tmp/get-pip.py
    wine "$PYTHON_DIR/python.exe" /tmp/get-pip.py --quiet 2>/dev/null || true
    wineserver -w 2>/dev/null || true
    rm /tmp/get-pip.py
fi

PYINSTALLER="$WINEPREFIX/drive_c/Python311/Scripts/pyinstaller.exe"
if [ ! -f "$PYINSTALLER" ]; then
    echo "[pip] 安裝 PyQt6 + PyInstaller..."
    wine "$PYTHON_DIR/python.exe" -m pip install --upgrade PyQt6 pyinstaller --quiet 2>/dev/null || true
    wineserver -w 2>/dev/null || true
fi

echo "[PyInstaller] 開始打包..."
cd /src
wine "$PYTHON_DIR/Scripts/pyinstaller.exe" build.spec 2>&1

if [ -f /src/dist/StockTrader.exe ]; then
    cp /src/dist/StockTrader.exe /output/台股漲停交易系統.exe
    echo "[完成] EXE 已輸出至 /output/台股漲停交易系統.exe"
else
    echo "[錯誤] 找不到 /src/dist/StockTrader.exe"
    exit 1
fi
