# Skill：GUI 帳戶 polling 與成交統計

## 涉及方法
- `set_broker(broker)` — 接受 main.py 注入的 broker、初始化 polling
- `_stop_account_polling()` — 切換 broker 時清舊 polling
- `_on_account_snapshot(snap)` — 收到 polling 回呼 → dispatch_ui → `_render_account`
- `_render_account(snap)` — 把 AccountSnapshot 套到 UI 卡片 + 持倉表
- `_on_trade(d)` — engine `on_trade` 的接收端：更新計數、成交表、儀表板統計卡
- `_on_order_event / _on_fill_event / _on_strategy_event / _on_decision_event` — broker / engine 推送事件

## `set_broker(broker)` 流程
1. `_stop_account_polling()` 收掉前一個 broker 的 polling。
2. 記錄 `self.broker = broker`。
3. 若 broker 已 connected → `broker.account_service().start_polling(self._on_account_snapshot, interval=10)`。
4. 訂閱 broker callback：`broker.on_order(self._on_order_event)` / `broker.on_filled(self._on_fill_event)`。
5. 更新 `order_mode_badge`、`_refresh_broker_status`、`_update_mock_mode_label`。

## `_render_account(snap)`
- `stat_available` = `buying_power`。
- `stat_realized` = `today_realized_pnl` 與漲跌色號（紅 / 綠）。
- `stat_positions` = `len(positions)`。
- 同步刷新 `positions_full_table`：每列 `code / name / qty / avg_cost / last_price / unrealized_pnl / unrealized_pnl_pct / 狀態`。

## `_on_trade(d)`
- 累計：`_trade_count / _buy_count / _sell_count / _daily_trade_codes`。
- `realized_total` 為更新後的當日已實現損益（由 engine 計算後傳入）。
- 更新 `stat_pnl_today / stat_return / stat_trade_cnt`。
- `_append_trade_row(...)` 寫入「成交記錄」表。

## 注意事項
- polling 間隔請維持 ≥ 5 秒（避免打爆 SDK）。
- 切換 broker（Mock ↔ Fubon）一定要先 `_stop_account_polling()`，否則舊 polling thread 仍存活，會把錯帳戶資料寫進 UI。
- `_render_account` 的計算不要與 engine 重複；以 broker snapshot 為主，engine `_today_realized_pnl` 為輔。
