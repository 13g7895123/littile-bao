# Skill：GUI 驗證腳本（`verify_*.py`）

> 屬於開發 / QA 用的「半自動腳本」，**不在正式打包流程內**。

## 檔案位置（皆位於 `build_win/src/`）
- `verify_dashboard.py`
- `verify_dashboard_v2.py`
- `verify_gui.py`
- `verify_logic.py`

## 共同特性
- 直接 `import gui`、`import broker`。
- 用 `unittest.mock` 包 `MockAdapter` / `FubonAdapter.from_config` / `scan_daily` 等。
- 走 `QApplication` 但**不 exec**；只驗證 UI 行為 / 邏輯後 `sys.exit(0/1)`。
- 任何斷言失敗 → `print("FAILURE: ...")` + `sys.exit(1)`。

## 各檔重點

### `verify_dashboard.py`
- 建立一個 MockAdapter，把 `load_symbol_info` 設為回傳 `2382` 一檔。
- patch `gui.scan_daily` 確保預覽流程也回那檔。
- 設定價格區間 250~400 後，呼叫 `App._collect_config / _load_dashboard_preview_summary / _apply_dashboard_preview_summary`。
- 斷言：monitor_table 至少含 `2382`，不含 `2317 / 2603`。

### `verify_dashboard_v2.py`
- v2 版本：用更貼近真實的 SymbolInfo 結構驗證更新後的 dashboard 邏輯。

### `verify_gui.py`
- 純啟動 GUI 並做基本元素檢查，協助回歸測試 UI 是否能正常初始化。

### `verify_logic.py`
- 驗證券商連線測試的成功 / 失敗兩條路徑。
- patch `broker.FubonAdapter.from_config` 模擬 SDK 行為，驗證 `_broker_test_connection` 的 UI 文字更新。

## 注意事項
- 這些腳本**不是 unit test**：不會被 `pytest` 自動收集，需手動執行。
- 用於回歸測試 GUI / 連線邏輯時很方便；若 GUI / broker API 改名，請先把這些腳本一起更新。
