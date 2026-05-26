# Skill：`FubonOrderManager`

## 檔案位置
- `build_win/src/broker/orders.py`

## 主要職責
- 呼叫 `fubon_neo` SDK 真實下單 / 撤單。
- 將內部 `OrderRequest` 轉換為 SDK `Order` 物件。

## `place_order(req)` 流程
1. 確認 `adapter.state == "connected"`，否則 `FubonNotLoggedInError`。
2. 動態 import `fubon_neo.constant.{BSAction, OrderType, MarketType, PriceType, TimeInForce}` 與 `fubon_neo.sdk.Order`，失敗 → `FubonOrderError`。
3. 建立 `Order(...)` 物件，欄位對應：
   - `buy_sell` = `BSAction.Buy/Sell`
   - `symbol` = `req.code`
   - `price` = `str(req.price)`
   - `quantity` = `req.qty * 1000`
   - `market_type` = `MarketType.Common`
   - `price_type` = `PriceType.Limit / Market`
   - `time_in_force` = `getattr(TimeInForce, req.time_in_force, TimeInForce.ROD)`
   - `order_type` = `OrderType.DayTrade if day_trade else OrderType.Stock`
   - `user_def` = `req.note[:8]`
4. `sdk.stock.place_order(account, order)`；失敗 → `FubonOrderError(message)`。
5. 回傳 `res.data.order_no` 字串。

## `cancel_order(order_id)`
- 呼叫 `sdk.stock.cancel_order(account, order_id)`，回 `res.is_success` 布林值。

## 注意事項
- 真正成交回報走 `FubonAdapter._attach_sdk_fill_handler() → dispatch_fill`，**這裡不直接 dispatch**。
- 修改下單欄位時，務必查最新 SDK 文件，避免常數變動（`BSAction` / `OrderType` 等）。
- `user_def` 由富邦規定最多 8 碼。
