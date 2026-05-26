# Skill：下單抽象 `OrderManager` + `OrderRequest`

## 檔案位置
- `build_win/src/broker/orders.py`

## 主要職責
- 定義跨適配層的下單請求 DTO `OrderRequest`。
- 定義抽象介面 `OrderManager`：`place_order / cancel_order` 與選擇性的 `modify_price / modify_qty`。
- 委託 / 成交事件透過 `BrokerAdapter.dispatch_order / dispatch_fill` 廣播。

## `OrderRequest` 欄位
| 欄位 | 預設 | 說明 |
|------|------|------|
| `code` | — | 股票代號（必填） |
| `name` | "" | 股票名稱（供 log/UI） |
| `side` | `OrderSide.BUY` | BUY / SELL |
| `price` | `Decimal("0")` | 限價；MARKET 單可為 0 |
| `qty` | 1 | 張數（一張 1000 股） |
| `order_type` | `"LIMIT"` | `LIMIT` / `MARKET` |
| `time_in_force` | `"ROD"` | `ROD` / `IOC` / `FOK` |
| `day_trade` | True | 是否現股當沖 |
| `note` | "" | 自訂註記（Fubon `user_def`，最多 8 碼） |

`__post_init__` 驗證：`qty > 0`、`LIMIT` 必須帶 `price > 0`。

## `OrderManager` 抽象介面
- `place_order(req)` → `order_id`
- `cancel_order(order_id)` → bool
- `modify_price(order_id, new_price)` / `modify_qty(order_id, new_qty)`：預設 `NotImplementedError`

## 對外公開的具體實作
| 類別 | 適用情境 | 對應 skill |
|------|----------|------------|
| `MockOrderManager` | 無 SDK / 測試 | [`mock_order_manager.skill.md`](./mock_order_manager.skill.md) |
| `DryRunOrderManager` | 已登入真實券商，但不送單；寫 audit log | [`dry_run_order_manager.skill.md`](./dry_run_order_manager.skill.md) |
| `FubonOrderManager` | 真實下單 | [`fubon_order_manager.skill.md`](./fubon_order_manager.skill.md) |

## 與其他模組關係
- `BrokerAdapter.place_order / cancel_order` 委派給 `_get_order_manager()`。
- `engine.TradingEngine._do_sell` / 進場流程透過 `adapter.place_order(req)` 送單。
- 成交回報 → `dispatch_fill` → `engine._on_broker_fill / gui._on_fill_event`。

## 注意事項
- 新增 `OrderRequest` 欄位時，確保三種 OrderManager 都能支援或忽略。
- 切換 `dry_run` 旗標時，記得呼叫 `adapter.set_dry_run(...)` 以重建 OrderManager。
