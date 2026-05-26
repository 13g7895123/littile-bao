# Skill：`DryRunOrderManager`

## 檔案位置
- `build_win/src/broker/orders.py`

## 主要職責
- 已成功登入真實券商但不發送真實委託；用於：
  - 上線前的策略全流程驗證。
  - 真實行情下的模擬交易。
- 為每筆下單 / 成交 / 取消寫入 `dry_run_audit_<YYYYMMDD>.jsonl` 審計檔。
- 可選擇用最新行情價作為成交價（`use_market_price=True`，呼叫 `adapter.latest_price(code)`）。

## 建構參數
| 參數 | 說明 |
|------|------|
| `adapter` | 必填，需處於 `CONNECTED` 狀態 |
| `fill_delay_range` | 預設 `(0.5, 1.5)`；負值會自動 clamp |
| `audit_dir` | 空字串 → 使用預設位置（exe 或 build_win 同層） |
| `use_market_price` | True → 嘗試以 `adapter.latest_price(code)` 取成交價，否則使用委託價 |

## 主要方法
- `place_order(req)`：未登入 → `FubonNotLoggedInError`；廣播 `PENDING`、寫 audit、排程 `_simulate_fill`。
- `_simulate_fill(order_id)`：若未取消，依 `_resolve_fill_price` 廣播 `FILLED + FillEvent`、寫 audit。
- `cancel_order(order_id)`：廣播 `CANCELLED` 並寫 audit。

## 審計檔格式（NDJSON）
每行：
```json
{
  "ts": "ISO timestamp",
  "type": "PLACE|FILL|CANCEL",
  "order_id": "DRY...",
  "code": "2330",
  "name": "...",
  "side": "BUY|SELL",
  "price": "1100.0",
  "qty": 1,
  "order_type": "LIMIT",
  "time_in_force": "ROD",
  "day_trade": true,
  "note": "...",
  "source": "DRY"
}
```

## 注意事項
- `order_id` 前綴 `DRY`。
- audit 寫檔走 `self._audit_lock`，可被多執行緒呼叫。
- `use_market_price=True` 時，`adapter` 必須提供 `latest_price(code)` 方法；否則退回委託價。
