# Skill：`FubonRealtimeFeed`

## 檔案位置
- `build_win/src/broker/realtime.py`

## 主要職責
- 透過 `fubon_neo` SDK 的 WebSocket 訂閱 trades + books。
- 自動拆分多條 WebSocket 連線（每條最多 200 訂閱、最多 5 條，最多 500 支），維持 SDK 限制。
- 解析推播訊息為 `TickEvent / BookEvent`，emit 給 engine。
- 內建 reconnect / 重新登入：遇到「underlying connection is closed」等錯誤時自動重登。
- 可選掛載 `RecordingWriter` 進行盤中錄製（攔截 `_emit_tick / _emit_book` + raw 訊息）。

## 初始化參數
- `adapter`：`FubonAdapter`
- `mode`：`"speed"` (預設) 或 `"normal"`，會對應到 SDK `Mode.Speed / Mode.Normal`
- `channels`：預設 `("trades", "books")`
- `ws_client_factory`：注入用，測試替換 WebSocket client 建立邏輯

## 主要方法
| 方法 | 行為 |
|------|------|
| `subscribe(codes, meta)` | 去重、上限截斷、寫入 `_subscribed`；已啟動則立刻訂閱 |
| `start()` / `_start_once()` | 拉 SDK token、`init_realtime()`、建立 WebSocket clients、訂閱 |
| `stop()` | 對每條 WebSocket 呼叫 `disconnect()`；清空 |
| `attach_recorder(recorder, record_raw=True)` | 注入 `RecordingWriter`；emit 與 raw 都會錄 |
| `_do_subscribe()` | 把 `_subscribed` 切 chunk、逐條 ws subscribe |
| `_on_raw_message(msg)` | 入口：寫 raw 錄製、抽 payload、依 event/channel 分派 |
| `_dispatch(event, data)` | 將 `data` 轉成 `TickEvent / BookEvent`，呼叫 `_to_tick / _to_book` |
| `_to_tick(p)` / `_to_book(p)` | 解析 SDK payload 欄位 |
| `_is_connection_dead_error / _can_relogin / _relogin` | 遇到底層連線死掉時的重登流程 |

## 連線拆分
- `_symbols_per_connection() = SUBSCRIPTION_LIMIT_PER_CONNECTION / len(channels)` = 200 / 2 = 100。
- `_symbol_chunks()`：把 `_subscribed` 切成多段，每段 ≤ 100。
- `_required_connection_count()`：chunks 數量但封頂 5。
- `_ensure_ws_clients(sdk, required_count)`：補足 ws；第 1 條優先用 `marketdata.websocket_client.stock`，其餘以 `build_websocket_client + realtime token` 建立。

## 與其他模組關係
- 由 `FubonAdapter.create_realtime_feed()` 建立。
- `engine.TradingEngine` 訂閱 tick / book。
- `gui` 經由 `_maybe_attach_recorder()` 把 `RecordingWriter` 接上。

## 注意事項
- 控制類事件（`authenticated / heartbeat / pong / subscribed / unsubscribed / ticker / error / info`）一律忽略。
- 收到 `event='data'` + `channel='trades' or 'books'` 才視為行情資料。
- callback 內部包 `try/except`，避免單筆訊息壞掉影響整個 stream。
- 重登策略只重試一次（避免無限迴圈），失敗包成 `FubonNetworkError`。
- 加新欄位 / 新 channel：
  - 更新 `_dispatch / _to_tick / _to_book`。
  - 同步調整 `FUBON_REALTIME_CHANNELS` 與相關上限。
