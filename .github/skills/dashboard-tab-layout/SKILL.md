---
name: dashboard-tab-layout
description: >-
  **GUI 技能** — 儀表板分頁配置與頁面資料邊界。
  使用時機：調整 `build_win/src/gui.py` 的主分頁、策略設定分頁、儀表板區塊、
  委託/成交、持倉部位、事件日誌頁面，或排查分頁切換後表格/日誌沒有更新。
  不適用：策略進出場邏輯（看 F1~F13 技能）、富邦 API 串接（看 stock-order-api）。
applyTo:
  - "build_win/src/gui.py"
  - "build_win/src/tests/test_gui_tabs.py"
  - "docs/儀表板分頁測試方案.md"
---

# Dashboard Tab Layout — 儀表板分頁配置

## 1. 目標
主視窗的每個主要功能區都應存在於對應分頁內，不使用常駐左側設定欄。使用者點擊頁籤後，才顯示該頁籤的內容。

## 2. 目前分頁邊界
| 分頁 | 內容 | 主要屬性 |
|---|---|---|
| `dashboard` / 儀表板 | 統計卡、即時監控 | `stat_*` labels、`monitor_table` |
| `settings` / 策略設定 | 策略參數、進場/排除/出場設定、JSON 匯入匯出 | `_fields`、`_checks`、`_toggles`、`_combos` |
| `broker` / 券商設定 | 富邦帳號、憑證、API Key、連線控制 | `_bfields`、`_broker_*` |
| `orders` / 委託/成交 | 委託狀態、成交記錄 | `orders_full_table`、`trades_full_table` |
| `positions` / 持倉部位 | 持倉表與損益小計 | `positions_full_table` |
| `events` / 事件日誌 | 日誌全文與清除按鈕 | `events_full_log` |
| `risk` / 風控設定 | 目前保留為後續獨立風控頁 | `_pages["risk"]` |

## 3. 實作準則
- 不要把策略設定常駐在主體左側；策略設定欄位應掛在 `settings` 分頁內。
- `dashboard` 只放總覽與即時監控，不再放事件日誌、持倉、委託、成交的縮小版。
- 完整頁面的表格是可見資料來源；若保留舊屬性名稱（如 `orders_table`），應 alias 到完整表格並避免重複同步插入。
- `_switch_tab()` 只負責切換可見頁與必要資料刷新；不要在切換時清空同一張表格。
- 跨執行緒 GUI 更新仍需走 `_dispatch_ui()`，不要從 broker 或 engine callback 直接寫 Qt widget。

## 4. 測試入口
單獨跑分頁測試：
```bash
cd build_win/src
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_gui_tabs -v
```

完整回歸：
```bash
cd build_win/src
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

## 5. 常見問題
- **切到委託/成交後表格變空**：檢查 `_sync_orders_full_table()` 是否對同一張 alias 表格執行 `setRowCount(0)`；同表格應直接 return。
- **日誌出現兩次**：檢查 `event_log` 與 `events_full_log` 是否為同一個 widget；若是同一個，不要再 mirror append。
- **策略設定沒有套用**：確認欄位仍寫入 `_fields` / `_checks` / `_toggles`，且 `_apply_config()`、`_collect_config()` 使用相同 key。