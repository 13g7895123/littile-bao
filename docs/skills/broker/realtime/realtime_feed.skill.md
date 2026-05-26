# Skill：`RealtimeFeed` 抽象介面 + `SymbolMeta`

## 檔案位置
- `build_win/src/broker/realtime.py`

## 主要職責
- 對 engine 提供統一的「即時行情訂閱」介面，不在乎底層是 SDK 還是 Mock。
- 支援雙 callback：`on_tick(cb)`、`on_book(cb)`。
- 支援注入 GUI log callback（`set_log_callback`）。

## 主要型別
- `RealtimeFeed`（ABC）
- `SymbolMeta(dataclass)`：訂閱用個股 meta，包含 `code / limit_up / prev_close / open_limit_up`
- `TickCallback = Callable[[TickEvent], None]`
- `BookCallback = Callable[[BookEvent], None]`

## 模組常數
| 名稱 | 值 | 說明 |
|------|----|------|
| `FUBON_REALTIME_SUBSCRIPTION_LIMIT_PER_CONNECTION` | 200 | 每條連線最多訂閱數 |
| `FUBON_REALTIME_MAX_CONNECTIONS` | 5 | 最多 5 條 WebSocket |
| `FUBON_REALTIME_CHANNELS` | `("trades", "books")` | 訂閱頻道 |
| `FUBON_REALTIME_SYMBOL_LIMIT` | 500 | 上限 = 200×5÷2 |

## 必要實作（子類）
- `start()`：啟動行情背景執行緒 / WebSocket。
- `stop()`：清乾淨。
- `subscribe(codes, meta)`：把 codes 加入訂閱清單；`meta: Dict[code, SymbolMeta]`（Mock 用到，Fubon 可忽略）。

## 共用方法
- `_emit_tick(ev)` / `_emit_book(ev)`：呼叫 callback；callback 拋例外時透過 `_log("ERROR", ...)` 通知 GUI。
- `_log(level, msg)`：同時送 `logging.getLogger("broker.realtime")` 與注入的 log_cb。

## 與其他模組關係
- `BrokerAdapter.create_realtime_feed()` 是工廠入口。
- `engine.TradingEngine` 在 `start()` 時呼叫 `feed.subscribe(...)` + `feed.start()`，並透過 `feed.on_tick / on_book` 餵 `_on_tick / _on_book`。
- `gui.App._maybe_attach_recorder()` 會把 `RecordingWriter` 經由 `FubonRealtimeFeed.attach_recorder` 接上行情流。

## 注意事項
- 不要在 callback 內做重 IO；callback 由 SDK 執行緒呼叫，會擋住下一筆訊息。
- 新增 channel 時請同時調整 `FUBON_REALTIME_CHANNELS` 與訂閱上限計算。
