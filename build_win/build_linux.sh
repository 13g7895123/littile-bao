#!/usr/bin/env bash
set -e

# ──────────────────────────────────────────────────────────────
#  台股漲停交易系統 — 在 Linux 上交叉編譯 Windows exe（PyQt6 版）
#  方式：用 Docker + Wine + Python 3.11 Windows 進行打包
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE="local/stock-trader-builder"
EXE_SRC="dist/windows/StockTrader.exe"
EXE_DST="dist/windows/台股漲停交易系統.exe"

echo "========================================"
echo " 台股漲停交易系統 — Linux 交叉編譯 Windows exe"
echo "========================================"
echo ""

if ! command -v docker &>/dev/null; then
    echo "[錯誤] 找不到 Docker，請先安裝 Docker"
    exit 1
fi

mkdir -p dist/windows

# 建置 Docker image（含 Wine + Python 3.11 Windows + PyQt6）
echo "[1/4] 建置 Docker image（首次需要 10~20 分鐘）..."
docker build -t "$IMAGE" .

# 執行打包
echo "[2/4] 執行 Windows 打包..."
docker run --rm --privileged \
    -v "$SCRIPT_DIR/src:/src" \
    -v "$SCRIPT_DIR/build.spec:/src/build.spec" \
    -v "$SCRIPT_DIR/dist/windows:/output" \
    "$IMAGE"

echo ""
if [ -f "$EXE_DST" ]; then
    SIZE=$(du -h "$EXE_DST" | cut -f1)
    echo "========================================"
    echo " 打包完成！"
    echo " 執行檔：${EXE_DST} (${SIZE})"
    echo "========================================"
else
    echo "[備用方案] Docker 打包失敗，請在 Windows 執行 build.bat"
    echo "  或在 Windows 執行："
    echo "  pip install PyQt6 pyinstaller"
    echo "  pyinstaller build.spec"
    exit 1
fi
