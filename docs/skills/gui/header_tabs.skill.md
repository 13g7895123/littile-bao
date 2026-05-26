# Skill：GUI 標題列 + 分頁切換

## 涉及方法
- `_build_header(root)` / `_tick_clock`
- `_set_badge_active / _set_badge_loading / _set_strategy_status`
- `_switch_tab(key)`
- `_set_tab_visible(key, visible)`

## 標題列內容（由左到右）
- 文字：「打板策略系統」
- `order_mode_badge` — 「模擬下單 / 實單交易」
- 分頁按鈕（`_tab_btns`）：`dashboard / settings / broker / orders / positions / events / limitup_test / decision_detail / risk`
  - 部分分頁預設隱藏（如 `risk`）：`self._hidden_tabs = {"risk"}`
- `strategy_badge`（QPushButton）：策略狀態（已啟用 / 已停用 / 載入中）
- `clock_lbl`：時鐘（每秒 `_tick_clock`）

## 分頁切換 `_switch_tab(key)`
- 依 key 顯示對應 `_pages[key]`、隱藏其他。
- 切換時做 lazy refresh：
  - `orders` → `_sync_orders_full_table`
  - `positions` → `_sync_positions_full_table`
  - `limitup_test` → `_refresh_limitup_test_page`

## 動態顯示 / 隱藏分頁
- `_set_tab_visible(key, visible)`：用於決策明細頁的開關（`_toggle_decision_detail_tab`）。
- 隱藏時若使用者目前在該分頁，會自動切回 `dashboard`。

## 注意事項
- 加新分頁須同時更新：
  - `_tab_btns` 順序與顯示文字（`_build_header.tabs`）。
  - `_pages` 字典（`_build_body`）。
  - `_switch_tab` 的 lazy refresh hook（若需要）。
- `strategy_badge` 3 種狀態與顏色集中在 `_set_badge_*`；勿散落樣式。
