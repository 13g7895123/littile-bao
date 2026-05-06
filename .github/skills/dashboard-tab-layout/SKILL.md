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
`dashboard` 分頁需保留原本總覽長相與功能，包含左側策略設定側欄、統計卡、即時監控、事件日誌、持倉、委託、成交小區塊。`settings` 分頁也要顯示同一份策略設定內容，但必須是滿版設定頁，不維持儀表板側欄的窄版樣式；其他分頁則顯示對應資訊的完整版本。

## 2. 目前分頁邊界
| 分頁 | 內容 | 主要屬性 |
|---|---|---|
| `dashboard` / 儀表板 | 原本總覽：左側策略設定、統計卡、即時監控、事件日誌、持倉、委託、成交 | `_strategy_settings_panel`、`stat_*` labels、`monitor_count_lbl`、`monitor_table`、`event_log`、`positions_table`、`orders_table`、`trades_table` |
| `settings` / 策略設定 | 滿版策略參數、進場/排除/出場設定、JSON 匯入匯出 | `_strategy_settings_panel`、`_fields`、`_checks`、`_toggles`、`_combos` |
| `broker` / 券商設定 | 富邦帳號、憑證、API Key、連線控制 | `_bfields`、`_broker_*` |
| `orders` / 委託/成交 | 委託狀態、成交記錄 | `orders_full_table`、`trades_full_table` |
| `positions` / 持倉部位 | 持倉表與損益小計 | `positions_full_table` |
| `events` / 事件日誌 | 日誌全文與清除按鈕 | `events_full_log` |
| `risk` / 風控設定 | 目前保留為後續獨立風控頁 | `_pages["risk"]` |

## 3. 實作準則
- `dashboard` 保留原本總覽功能，不要移除左側策略設定、事件日誌、持倉、委託、成交小區塊。
- `settings` 分頁使用滿版設定頁，不要保留 270px 側欄寬度限制；目前透過 `_place_strategy_settings_panel()` 在儀表板側欄與滿版設定頁之間移動同一份 widget。
- 完整分頁表格應獨立於儀表板小表格，並由 `_append_order()`、`_append_trade()`、`_render_account()`、`_append_log()` 即時同步。
- 即時監控標題旁需顯示目前表格總檔數（`monitor_count_lbl`，文字格式 `共 N 檔`），由 `_render_monitor()` 每次刷新同步更新。
- 即時監控表格需在 `_render_monitor()` 後呼叫欄寬自動調整，讓代碼、名稱、價格、狀態、動作等內容盡量完整顯示；若欄位總寬超出區塊，允許水平捲動。
- 即時監控 `動作` 欄目前是狀態指引文字，不是可點擊按鈕。內容應描述下一步可做/會做的事，例如 `等待漲停`、`等待封板`、`檢查進場`、`等委賣降`、`等待成交`、`監控出場`、`已封鎖`。
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
- **切到委託/成交後表格變空**：檢查 `_sync_orders_full_table()` 是否從儀表板小表格複製到完整表格，而不是反向清空來源。
- **日誌出現兩次或沒有同步**：檢查 `event_log`（儀表板小區塊）與 `events_full_log`（事件日誌分頁）是否為不同 widget，且 `_append_log()` 有同步追加兩邊。
- **策略設定頁仍像側欄**：檢查 `_set_strategy_panel_mode(full_page=True)` 是否解除 `maximumWidth`，且 panel 背景切回 `C["bg"]`。
- **策略設定沒有套用**：確認欄位仍寫入 `_fields` / `_checks` / `_toggles`，且 `_apply_config()`、`_collect_config()` 使用相同 key。
- **即時監控內容被截斷**：檢查 `_autosize_monitor_columns()` 是否在 `_render_monitor()` 結尾被呼叫，且 `monitor_table` 沒有把最後一欄強制 stretch 造成其他欄位被壓縮。