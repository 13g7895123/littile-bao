# Skill：engine 對 broker 回報的處理

## 檔案位置
- `build_win/src/engine.py`

## 涉及方法
- `_on_broker_order(ev: OrderEvent)`
- `_on_broker_fill(ev: FillEvent)`
- 訂閱位置：`start()` 內 `broker.on_order(self._on_broker_order)` + `broker.on_filled(self._on_broker_fill)`

## `_on_broker_order(ev)`
- 寫 `on_log("INFO", ...)` 表達 `委託 BUY/SELL N 張 @ price 狀態=...`。
- 同時 `_emit_decision_event("ORDER", state, f"委託{status}", side, {order_id, qty, filled_qty, price, status, source}, event_time=ev.time)`。
- 即便 `state` 找不到，仍會嘗試寫 log，避免漏訊。

## `_on_broker_fill(ev)`
1. 以 `(order_id, side, code, price, qty, time)` 組 `fill_key`，**去重**避免同一筆被重複處理。
2. 找到對應 `state`；無 → return。
3. **BUY**：
   - `pending=False`、`position_qty += qty`、`entry_blocked_reason=""`。
   - 平均成本更新：第一次以 `ev.price` 為基準；加碼以加權平均。
   - 維護 `_daily_trade_codes / _daily_trade_count`。
   - `on_log("INFO")` + `on_trade({action:"BUY", time, detail_time, ...})` + `_emit_decision_event("FILL", state, "買進成交", "BUY", {...})`。
4. **SELL**：
   - 計算 `realized_pnl(entry_price, ev.price, qty, day_trade=True)`；累加 `_today_realized_pnl`。
   - `position_qty -= qty`；歸零時設 `entry_blocked / entry_blocked_reason="已賣出" / sold_today=True / entry_price=None`。
   - `on_trade({action:"SELL", time, detail_time, pnl, realized_total, note})`、`_emit_decision_event("FILL", state, "賣出成交", note, {...})`。

## 注意事項
- 與 `_do_sell` 的「無 broker」路徑不同：有 broker 時 PnL 結算只在這裡發生，不在送單時。
- `fill_key` 時間欄使用 `isoformat()`，若 SDK 回傳沒 time，去重會以空字串為值。
- 加新 `OrderStatus` / `OrderSide` enum 值時，需檢查這裡的字串比對是否仍有效。
- `on_trade` 與 `_emit_decision_event` 都是 best-effort：callback 失敗會被 swallow。
