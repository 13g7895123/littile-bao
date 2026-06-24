# Little Bao Project

這個 repo 的主體是一個以 Python + PyQt6 實作的桌面交易程式，並附帶券商整合、策略引擎、Windows 打包流程，以及幾個獨立診斷工具。

## 目錄

- `build_win/src/`: 主要應用程式原始碼
- `build_win/src/main.py`: GUI 應用入口
- `build_win/src/bootstrap.py`: 啟動前檢查、logging、Windows 校時、broker 初始化
- `build_win/src/broker/`: 券商抽象層與 Fubon / Mock 實作
- `build_win/src/tests/`: 單元測試
- `build_win/`: PyInstaller 與跨平台打包腳本
- `isolated_fubon_latency_probe/`: 獨立延遲探針工具
- `docs/`: 交易紀錄、設計說明、維運文件
- `extracted/`: 歷史抽取程式碼或參考版本

## 啟動

安裝依賴：

```bash
python3 -m pip install -r build_win/requirements.txt
```

執行主程式：

```bash
cd build_win/src
python3 main.py
```

執行測試：

```bash
cd build_win/src
python3 -m unittest
```

## 目前分層

- `main.py` 只保留應用組裝與 GUI 啟動。
- `bootstrap.py` 集中處理啟動流程，避免入口檔混入過多平台與初始化細節。
- `engine.py` 仍是主要策略核心。
- `gui.py` 仍偏大，後續建議繼續拆成 `gui/` 子模組。

## 下一步建議

- 將 `gui.py` 拆成頁面、元件、樣式與事件橋接模組
- 將 `engine.py` 內的資料模型與策略判斷抽離
- 補 `pyproject.toml`，逐步移除 `sys.path` 手動調整
- 將執行期產物與臨時報告移到統一的 `artifacts/` 或工作資料夾
