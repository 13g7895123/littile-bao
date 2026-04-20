#!/usr/bin/env bash
set -e

# ──────────────────────────────────────────────────────────────
#  台股漲停交易系統 — 在 Linux 上交叉編譯 Windows exe
#  使用 Docker (cdrx/pyinstaller-windows) 進行打包
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE="cdrx/pyinstaller-windows:python3"
EXE_NAME="台股漲停交易系統"

echo "========================================"
echo " 台股漲停交易系統 — Linux 交叉編譯 Windows exe"
echo "========================================"
echo ""

# 檢查 Docker
if ! command -v docker &>/dev/null; then
    echo "[錯誤] 找不到 Docker，請先安裝 Docker"
    exit 1
fi

# 清理舊的輸出
echo "[1/3] 清理舊的 build/dist 目錄..."
rm -rf dist build

# 拉取映像（若本地沒有）
echo "[2/3] 確認 Docker 映像..."
if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "       正在下載映像（首次需要幾分鐘）..."
    docker pull "$IMAGE"
fi

# 執行打包
echo "[3/3] 開始打包..."
docker run --rm \
    -v "$SCRIPT_DIR:/src" \
    "$IMAGE" \
    --onefile \
    --noconsole \
    --name "$EXE_NAME" \
    --paths src \
    --hidden-import tkinter \
    --hidden-import tkinter.ttk \
    --hidden-import tkinter.scrolledtext \
    --hidden-import tkinter.messagebox \
    --hidden-import tkinter.font \
    --hidden-import json \
    --hidden-import threading \
    --hidden-import queue \
    --hidden-import random \
    --hidden-import collections \
    --hidden-import dataclasses \
    --exclude-module shioaji \
    --exclude-module numpy \
    --exclude-module pandas \
    --exclude-module matplotlib \
    src/main.py

echo ""
if [ -f "dist/${EXE_NAME}.exe" ]; then
    SIZE=$(du -h "dist/${EXE_NAME}.exe" | cut -f1)
    echo "========================================"
    echo " 打包完成！"
    echo " 執行檔：dist/${EXE_NAME}.exe (${SIZE})"
    echo "========================================"
else
    echo "[錯誤] 打包失敗，找不到輸出檔案"
    exit 1
fi
