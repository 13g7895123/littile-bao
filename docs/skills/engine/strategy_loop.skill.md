# Skill：engine 策略主迴圈與進出場決策

## 檔案位置
- `build_win/src/engine.py`

## 涉及方法
- `_loop()`
- `_maybe_daily_reset()`
- `_tick(state, now)`：每秒對單檔做的決策
- `_do_sell(state, info, note)`
- `_open_ticks_from_limit(state)`
- `_block_entry / _skip_entry`
- `_confirm_buying_power / _confirm_special_stock_status`
- `_tick_size / _parse_config_time / _current_datetime`

## `_loop()` 概覽
- 由 `start()` 在 daemon thread 啟動。
- 每秒：
  1. `_maybe_daily_reset()`：跨日重置 `_daily_trade_codes / _today_realized_pnl / _trading_date`。
  2. 對 `_states.values()` 一一呼叫 `_tick(state, now)`。
  3. 把 `_state_snapshot_details(...)` 集合丟給 `on_status(snapshot_list)`。

## `_tick(state, now)` 規則（依執行順序）

1. **1 秒視窗自然衰減**（即使沒有新 tick 也清舊資料）。
2. **F9（價格區間）**：用 `info.limit_up` 對 `[price_min, price_max]` 做軟性 skip。
3. **F6（排隊取消）**：`pending` 且 `last_1s_vol > volume_spike_cancel_threshold` → 取消委託 + `entry_blocked="爆量取消"`。
4. **出場（有部位 + 非 pending）**：
   - **F4**（漲停板打開）：需 `touched_limit_up_today or candle_index > 0`（或 `f4_require_today_limitup=False`）；`open_ticks ≥ f4_open_ticks_to_sell` → 賣出。
   - **F5**（1 秒爆量）：`last_1s_vol > volume_spike_sell_threshold` → 賣出。
5. **進場前置**：
   - 跳過：`pending / entry_blocked / candle_index == 0 / 未鎖板 / startup_limitup_blocked`。
   - **F12**：開盤即漲停且當日已賣過 → skip。
   - 「開盤即漲停獨立開關」`f_open_limitup_entry_enabled=False` → 該股 skip。
   - **F13**：當日成交檔數已達上限 → skip。
6. **進場規則**（可組合）：
   - **消化量進場**：`f_consume_enabled` 啟用且 `limit_up_consumed_qty < threshold` → skip；否則加入策略 ID。
   - **F1（時間 + 委賣張數）**：
     - 與消化量互斥條件：`f_consume_enabled & consume_mutex_with_f1` → 不套用 F1。
     - 時間需 `>= start_time` 且 `< entry_before_time`（最多到 13:30）。
     - `ask_qty_at_limit < ask_queue_threshold`。
   - **F7（K 棒上限）**：`candle_index > candle_limit` → skip。
   - **F10（價量雙確認）**：
     - `ask0_price` 必填。
     - `ask0_price ≥ limit_up * ask_price_ratio`。
     - `last_1s_vol ≥ entry_volume_confirm`。
7. **資金 / 計算張數**：`per_stock_amount // (limit_up * 1000)` = `qty`。
   - 不足或設定無效 → `_block_entry("資金不足")`。
8. **可用額度（券商實際）**：`_confirm_buying_power`；`order_dry_run=True` 時直接放行。
9. **特殊股（F11）**：`_confirm_special_stock_status` 會 refresh 一次特殊股旗標；命中 disposal / attention / day_trade_restricted → block。
10. **送單**：
    - 有 broker → 建立 `OrderRequest(BUY, limit_up_price)` 並呼叫 `broker.place_order(req)`。
    - 無 broker → 啟動 daemon thread 模擬填單（保留供測試 / 純離線）。

## `_do_sell(state, info, note)`
- 若有 broker：先呼叫 `broker.account_service().snapshot()` 確認券商實際庫存；
  - 庫存為 0 → 本地清零、不下賣。
  - 庫存 < 本地 → 以實際庫存為準。
- 用 `last_price`（缺則用漲停價）建立 `OrderRequest(SELL)` 並 `place_order`。
- 無 broker：直接更新 `position_qty=0 / sold_today=True`、計算 `realized_pnl` 累加 `_today_realized_pnl`、回呼 `on_trade`。

## 注意事項
- 「軟性 skip」用 `_skip_entry`（只記原因、不封鎖），「硬性 block」用 `_block_entry`。
- 修改任一功能編號時，**必同步更新 `TradingConfig` 對應欄位、GUI 顯示文案、相關測試**。
- 取消 / 出場後狀態要清乾淨（`pending=False, entry_blocked, sold_today` 等）。
- `_open_ticks_from_limit` 用 tick 表算「漲停板被打開幾檔」。

## 對應測試
- `build_win/src/tests/test_engine_strategy.py`
