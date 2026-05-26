# Skill：engine 核心物件

## 檔案位置
- `build_win/src/engine.py`

## 主要型別

### `StockInfo`
個股靜態資料（由 `SymbolInfo` 轉換而來）。
- `code, name, limit_up, market`
- 特殊股旗標：`is_disposal, is_attention, is_day_trade_restricted`
- 進階：`open_limit_up, prev_close, prior_limit_up_streak`

### `StockState`
策略運行時的個股狀態，**所有狀態變更需在 `engine._lock` 內進行**。

| 區塊 | 欄位 |
|------|------|
| 部位 | `position_qty, pending, entry_price, sold_today` |
| 進場控制 | `entry_blocked, entry_blocked_reason, last_skip_reason, candle_index` |
| 1 秒量視窗 | `last_1s_vol, tick_vols(deque[(ts, vol)])` |
| 漲停狀態 | `is_at_limit_up, touched_limit_up_today, today_limit_up_counted, limit_up_since, limit_up_consumed_qty` |
| Tick 即時值 | `last_price, ask0_price, ask0_volume, bid0_price, bid0_volume, ask_qty_at_limit` |
| Book 旗標 | `has_ask_levels, has_bid_levels` |
| Tick 旗標 | `trade_bid, trade_ask, trade_is_limit_up_price/bid/ask` |
| 鎖板評估 | `limit_up_signal_states, limit_up_candidate_states, active_limit_up_mode` |
| 其他 | `special_check_completed, initial_limit_up_checked, startup_limitup_blocked` |

### `MOCK_STOCKS`
- 引擎在無 `symbol_infos` 時退回的 10 檔測試清單；每檔 `StockInfo`。

### `TradingEngine`
- 入口物件，集合上述 callback、feed、broker、states、daily counters、limit_up_mode 等。
- 主要欄位：
  - `config: TradingConfig`、`feed: RealtimeFeed`、`broker: BrokerAdapter`
  - 4 個外部 callback：`on_log / on_trade / on_status / on_strategy_event / on_decision_event`
  - `_states: Dict[code, StockState]`、`_lock`
  - 計數：`_tick_recv_count / _book_recv_count / _tick_miss_count`、`_daily_trade_count / _daily_trade_codes`、`_today_realized_pnl`

## 注意事項
- `StockState` 新增欄位 → 必須同步在 `__init__` 初始化，避免讀取時 AttributeError。
- 不要在 callback 內保留對 `StockState` 的 reference 跨執行緒；統一用 `_states.get(code)` 取最新。
- 多執行緒進入點：`_on_tick / _on_book`（feed thread）、`_loop`（_thread）、`_on_broker_order/fill`（broker thread）、`sell_all_strategy_positions`（GUI thread）。
