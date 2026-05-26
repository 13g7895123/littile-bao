# Skill：engine 行情輸入與漲停狀態維護

## 檔案位置
- `build_win/src/engine.py`

## 涉及方法
- `_on_tick(ev)` — `RealtimeFeed.on_tick` 的接收端
- `_on_book(ev)` — `RealtimeFeed.on_book` 的接收端
- `_refresh_limit_up_state(state, *, source, now, event_time)`
- `_log_limit_up_signal_change(state, *, source, signals, event_time)`
- `_mark_limit_up_touched(state, now)`

## `_on_tick` 行為
1. 累加 `_tick_recv_count`；若 `ev.code` 不在 `_states` → 記錄 miss 並 return（前 3 次與每 100 次寫 WARN）。
2. **忽略無效 tick**：`price <= 0` 視為盤前試撮 / 欄位缺漏，記錄但不更新狀態。
3. 維護 1 秒滑動視窗：`state.tick_vols.append((now, vol))`，pop 過期，重算 `last_1s_vol`。
4. 更新 `last_price`、`trade_bid/ask`、`trade_is_limit_up_*` 旗標。
5. 若成交價 ≥ 漲停 → `limit_up_consumed_qty += vol`。
6. 呼叫 `_refresh_limit_up_state(..., source="tick")`。

## `_on_book` 行為
1. 同樣鎖 `_lock`，找對應 state；找不到直接 return。
2. 更新 `ask0_price/volume`、`bid0_price/volume`、`has_ask_levels`、`has_bid_levels`。
3. 呼叫 `_refresh_limit_up_state(..., source="book")`。

## `_refresh_limit_up_state` 行為
- 呼叫 `limitup_detection.evaluate_limit_up_state(...)` 取得 `ask_qty_at_limit`、`signals`、`candidates`。
- 寫入 `state.limit_up_signal_states / limit_up_candidate_states`。
- 取 `mode = state.active_limit_up_mode or self._limit_up_mode`，看 `candidates[mode]` 判斷是否 sealed。
- **初次檢查**（`_started_at` 已設、`initial_limit_up_checked=False`）：
  - 若已 sealed → 設 `startup_limitup_blocked=True`、`last_skip_reason="程式啟用後已漲停"`，等鎖板撬開後才允許後續進場。
- 後續：
  - sealed → `is_at_limit_up=True`；若沒有 startup block，標記 `touched_limit_up_today=True` 並呼叫 `_mark_limit_up_touched`（更新 `candle_index` / `limit_up_since`）。
  - 不 sealed 但原本 sealed → 清掉 `is_at_limit_up`、清 `startup_limitup_blocked`。

## 注意事項
- 任何來源（tick / book）都會走 `_refresh_limit_up_state`，避免兩條來源各自評估造成不同步。
- `is_at_limit_up` 由 _refresh 統一寫，**不要在 `_on_tick` 內另算**。
- 動態切換 `active_limit_up_mode`（GUI「鎖板測試頁籤」可即時換）會立即反映到下一筆 tick / book。
- 加新訊號 → 更新 `evaluate_limit_up_state` 與此處的解析，並確保 `_log_limit_up_signal_change` 顯示完整。
