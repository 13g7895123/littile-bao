# Skill：GUI 儀表板分頁

## 涉及方法
- `_build_dashboard(parent)`
- `_build_stats_row(lay)`
- `_build_mid_row(lay)`
- `_build_bot_row(lay)`
- `_load_dashboard_preview_summary(broker, cfg)` / `_apply_dashboard_preview_summary` / `_preload_dashboard_preview_async`
- `_build_next_day_exclusion_rows / _log_next_day_exclusions / _is_after_market_close`

## 版面
- 左側嵌入「策略設定」側欄（`_create_strategy_settings_panel`），可動態切換為全頁設定（`_set_strategy_panel_mode`）。
- 右側分三段：
  - **統計卡列**（`_build_stats_row`）：6 張卡
    - `stat_pnl_today / stat_return / stat_realized / stat_positions / stat_trade_cnt / stat_available`
  - **中段**：左「即時監控表」(`monitor_table`)、右「事件日誌」(`event_log` + 篩選按鈕)
  - **下段**：持倉、委託、成交三個表（`_build_bot_row`）

## 即時監控表 `monitor_table`
- 欄位：`["代碼","名稱","價格","漲跌","漲跌幅","委賣張數","1秒成交量","起漲K","狀態","動作"]`
- 列來源：`engine.get_summary()` 透過 `on_status` 回呼 → `_apply_monitor_snapshot`（位於 trading_lifecycle 範圍）。
- 「狀態 / 動作」欄會反映 `entry_blocked / last_skip_reason / startup_limitup_blocked / sold_today / pending` 等資訊。

## 預覽載入（未啟動策略時）
- `_preload_dashboard_preview_async(broker=None)`：在背景跑 `_load_dashboard_preview_summary` 取得候選清單（用 `scan_preview_candidates`），列出可進場標的供使用者預檢。
- `_apply_dashboard_preview_summary` 把結果套用到 monitor_table（標示「預覽」狀態）。
- 收盤後（`_is_after_market_close`）會額外列出「依當日收盤推估，明天會被條件排除的標的」(`_build_next_day_exclusion_rows`)。

## 注意事項
- 修改 monitor 欄位數量 / 寬度時，更新 `cols` 與 `for i, w in enumerate([...]): setColumnWidth`。
- `monitor_count_lbl` 顯示「共 N 檔」需與表格實際列數保持同步。
- 預覽用流程在「未啟動策略」與「啟動後」的資料來源不同，切勿混用。
