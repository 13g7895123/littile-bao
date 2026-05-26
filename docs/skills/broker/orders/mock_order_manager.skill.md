# Skill：`MockOrderManager`

## 檔案位置
- `build_win/src/broker/orders.py`

## 主要職責
- 無券商 / Demo 用：以 `threading.Timer` 模擬完整委託 → 成交流程。
- 適合單元測試與 Mock 模式下的端到端流程驗證。

## 行為
- `place_order(req)`：
  1. 立即廣播 `OrderEvent(status=PENDING)`。
  2. 在 `(0.6 ~ 1.8 秒)` 內排程模擬成交。
- `_simulate_fill(order_id)`：若未被 cancel，廣播 `OrderEvent(status=FILLED)` 與對應 `FillEvent`。
- `cancel_order(order_id)`：將 id 加入 `_cancelled`，廣播 `OrderEvent(status=CANCELLED)`。

## 注意事項
- `order_id` 格式：`M{hex10}`。
- 延遲區間預設 `(0.6, 1.8)`，建構時可調整。
- 模擬成交的價格 = 委託價（不考慮市價變動）。
