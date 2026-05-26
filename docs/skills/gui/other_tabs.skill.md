# Skill：GUI 其餘分頁（委託 / 成交 / 持倉 / 事件 / 鎖板測試 / 決策明細）

## 涉及方法
- 委託 / 成交：`_build_orders_page`、`_sync_orders_full_table`、`_sync_trades_full_table`、`_append_order`、`_mark_order_filled`
- 持倉：`_build_positions_page`、`_sync_positions_full_table`、`_render_account`
- 事件日誌：`_build_events_page`、`_append_strategy_event`、`_sync_decision_tab_toggle_text`
- 鎖板測試：`_build_limitup_test_page`、`_refresh_limitup_test_page`、`_render_limitup_test_snapshot/_detail`、`_on_limitup_test_stock_changed/_mode_changed`、`_apply_selected_limitup_test_mode`、`_fmt_limitup_price/_fmt_limitup_mode_hits/_fmt_limitup_signal_hits`
- 決策明細：`_build_decision_detail_page`、`_append_decision_detail`、`_toggle_decision_detail_tab`、`_hide_decision_detail_tab`、`_clear_decision_detail`

---

## 委託 / 成交分頁
- `orders_full_table` 欄位：`["代碼","名稱","委託類別","價格","數量","掛單時間","成交時間","狀態","來源"]`
- `trades_full_table` 欄位：`["時間","代碼","名稱","類別","價格","數量","損益"]`
- 由 broker `_on_order_event / _on_fill_event` 推送 → `_append_order / _mark_order_filled / _on_trade` 更新。
- 顯示「成交總計」與「累計損益」於底部。

## 持倉分頁
- `positions_full_table` 欄位：`["代碼","名稱","持股數","成本價","現價","損益","損益率","狀態"]`
- 來源：`broker.account_service().start_polling(self._on_account_snapshot)`，每 10 秒。
- `_render_account(snap)` 同時更新儀表板的 `stat_positions / stat_realized / stat_available` 卡片。

## 事件日誌分頁
- 上區「策略觸發紀錄」：`strategy_trigger_table`（接 `on_strategy_event`）。
- 下區「事件日誌」：`events_full_log`（接 `on_log` 同源）。
- 上區頭部有「顯示決策明細」按鈕，點擊呼叫 `_toggle_decision_detail_tab`，切換分頁可見性。

## 鎖板測試分頁 `limitup_test`
- 上區：表頭 + 「套用選取模式」按鈕（`_apply_selected_limitup_test_mode`）。
- 中區：股票列表 + 模式列表（兩個 QTableWidget 互動）。
- 下區：選定股票 / 模式 的即時 signals + candidates。
- 切換選取時 → `_on_limitup_test_stock_changed / _on_limitup_test_mode_changed`。
- 套用後呼叫 `engine.update_limit_up_mode(mode)`。
- signals 標籤對應 `LIMIT_UP_SIGNAL_LABELS`（在 `gui.py` 頂端）。

## 決策明細分頁 `decision_detail`
- 顯示 `on_decision_event` 推送的詳細決策事件。
- 欄位：時間 / 代碼 / category / result / reason / 部分 details 攤平。
- 預設**隱藏**；由「事件日誌」分頁的按鈕切換顯示。

## 注意事項
- 任何分頁變更欄位都要更新對應 `_sync_*_full_table` 的塞值邏輯，避免 column 對不齊。
- 表格列數變更時保持小計 / 摘要 label 同步。
- 「策略觸發紀錄」與「決策明細」雖然來源不同，但兩者皆受 `_log_filter` 影響：請保留 toggling 邏輯。
