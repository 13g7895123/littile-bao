# Skill：engine 事件與決策日誌

## 檔案位置
- `build_win/src/engine.py`

## 涉及方法
- `_log_strategy_trigger(side, state, strategy, details)`
- `_log_limit_up_signal_change(state, *, source, signals, event_time)`
- `_state_snapshot_details(state) -> dict`
- `_emit_decision_event(category, state, result, reason, details, *, event_time=None)`
- `_fmt_decision_value(value)`

## `_log_strategy_trigger`
- 三個動作：
  1. 呼叫 `on_strategy_event({"time", "side", "code", "name", "strategy", "details"})`。
  2. 呼叫 `_emit_decision_event("STRATEGY", state, {"BUY":"進場觸發","SELL":"出場觸發","CANCEL":"取消觸發"}, strategy, details)`。
  3. `on_log("TRADE", "[策略觸發][SIDE][CODE NAME] 策略=XXX；k=v, k=v")`。
- `details` 可包含 `Decimal`，會用 `str(...)` 轉字串避免 JSON 序列化問題。

## `_emit_decision_event`
- 只有當 `on_decision_event is not None` 才送。
- 內部會 merge `_state_snapshot_details(state)` 與 caller 提供的 `details`。
- `event_time` 用於覆寫時間欄位（取自 SDK 推送）；缺則用 `datetime.now()`。
- 所有 `Decimal / dict / list` 會經 `_fmt_decision_value` 轉換為 JSON-safe 結構。

## `_state_snapshot_details`
- 將 `StockState` 的關鍵欄位攤平成 dict，便於 GUI / log 顯示與比對：
  - `candle, limit_up_mode, is_at_limit_up, ask_qty, ask0/bid0, last_price, last_1s_vol, consume_qty, pending, position_qty, blocked / blocked_reason, sold_today, has_ask/bid_levels, limit_up_signals, limit_up_candidates`。

## Event category
| category | 觸發點 |
|----------|--------|
| `STRATEGY` | `_log_strategy_trigger` 內 |
| `ENTRY_BLOCK` | `_block_entry` |
| `ENTRY_SKIP` | `_skip_entry` |
| `ORDER` | `_on_broker_order` |
| `FILL` | `_on_broker_fill` |

## 注意事項
- 加新 category 時，請更新 GUI「決策明細」頁籤的色票 / 篩選邏輯。
- 若要新增「state snapshot」欄位，記得同時更新 `_state_snapshot_details` 與 `get_summary` 兩處。
- `_fmt_decision_value` 為遞迴呼叫；任何新型別請在這裡加 case，避免 GUI / 寫檔失敗。
