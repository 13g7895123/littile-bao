# Skill：engine 對外 API（GUI 使用）

## 檔案位置
- `build_win/src/engine.py`

## 建構介面
```python
TradingEngine(
    config: TradingConfig,
    on_log: Callable[[str, str], None],
    on_trade: Callable[[dict], None],
    on_status: Callable[[List[dict]], None],
    on_strategy_event: Optional[Callable[[dict], None]] = None,
    on_decision_event: Optional[Callable[[dict], None]] = None,
    feed: Optional[RealtimeFeed] = None,
    symbol_infos: Optional[Dict[str, SymbolInfo]] = None,
    broker: Optional[BrokerAdapter] = None,
)
```

- `symbol_infos=None` 時退回 `MOCK_STOCKS`。
- 篩出落在 `cfg.get_markets()` 的標的，建立 `StockState`，並把 `active_limit_up_mode` 設為解析過的 `_limit_up_mode`。

## 主要對外方法

| 方法 | 用途 |
|------|------|
| `start()` | 訂閱 broker callback / feed callback、啟動 `_loop` thread；log 啟用功能旗標 |
| `stop()` | 停 thread、停 feed、登出 broker |
| `update_limit_up_mode(mode)` | 即時更新 `_limit_up_mode`，並同步寫進所有 `state.active_limit_up_mode` |
| `replace_universe(new_symbol_infos)` | 熱替換 `_states`；保留持倉 / pending / 已 K 棒進場的標的，回傳 `{added, removed, kept_in_new, kept_protected}` |
| `resubscribe_feed()` | 依當前 `_states` 重建 `SymbolMeta` dict 並重新訂閱 |
| `sell_all_strategy_positions(reason)` | 手動賣出全部由策略持有的部位（回傳張數計算用） |
| `get_summary() -> List[dict]` | 給 GUI 輪詢的單檔快照；含價格、漲跌、鎖板 signals / candidates、`out_of_range`、`last_skip_reason` 等 |

## `get_summary()` 重要欄位
- `price` 永遠保留最後一次有效 socket 價；尚未收到 → `None`（UI 顯示「—」）。
- `change / change_pct`：以 `prev_close` 計算。
- `out_of_range`：F9 即時價過濾結果（GUI 用於隱藏或灰底顯示）。
- `limit_up_signals / limit_up_candidates`：給「鎖板測試頁籤」即時顯示。

## 對 GUI 的回呼合約
- `on_log(level, message)`：UI 寫進日誌頁籤。
- `on_trade(trade_dict)`：UI 加一筆「成交」行情。
- `on_status(snapshots: list[dict])`：每秒推一份 `get_summary()` 等價結果到 UI。
- `on_strategy_event(dict)`：策略觸發 BUY/SELL/CANCEL 時推；GUI 用於「事件日誌」頁籤。
- `on_decision_event(dict)`：更詳細的決策事件（含 state snapshot）；GUI「決策明細」頁籤使用。

## 注意事項
- 任何新增的 callback 都應走「`if cb is not None: try: cb(...) except: pass`」模式，避免單一 UI bug 影響交易迴圈。
- 熱替換 `replace_universe` 後務必再呼叫 `resubscribe_feed()`，否則 feed 仍訂閱舊清單。
- `update_limit_up_mode` 會立即影響下一筆 tick / book 評估結果，UI 切換預期是即時生效。
