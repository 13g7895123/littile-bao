# Skill：`BrokerAdapter` 抽象介面

## 檔案位置
- `build_win/src/broker/adapter.py`

## 主要職責
- 定義 engine / gui 看到的「統一券商介面」。
- 不論底層是 `FubonAdapter`（真實 SDK）還是 `MockAdapter`（無憑證），都實作這個介面。
- 維護：
  - 登入生命週期（`login / logout / state / account / select_account`）。
  - 行情訂閱物件工廠（`create_realtime_feed`）。
  - 個股基本資料載入（`load_symbol_info`）。
  - 委託 / 成交 callback 管理（`on_order / on_filled / dispatch_*`）。
  - 下單管理（`place_order / cancel_order`，背後委派給 `_get_order_manager()`）。

## 必須由子類實作（abstract）
- `login()` → `LoginResult`
- `logout()`
- `state` (property) → `ConnectionState`
- `account` (property) → `Optional[AccountRef]`
- `select_account(branch_no, account_no)` → `AccountRef`
- `create_realtime_feed()` → 一個 `RealtimeFeed` 實例
- `load_symbol_info(codes)` → `Dict[str, SymbolInfo]`

## 已實作的共用行為
| 方法 | 行為 |
|------|------|
| `on_filled(callback)` / `on_order(callback)` | 維護 `_fill_subs` / `_order_subs` 訂閱者清單 |
| `dispatch_fill(ev)` / `dispatch_order(ev)` | 廣播事件給所有訂閱者，吃掉個別 callback 例外避免影響其他訂閱者 |
| `place_order(req)` | 委派給 `_get_order_manager()`；子類需提供此方法 |
| `cancel_order(order_id)` | 同上 |

## 與其他模組關係
- `engine.TradingEngine` 透過 `adapter.on_filled / on_order` 訂閱事件。
- `gui.App.set_broker(...)` 設置目前使用的 adapter。
- `main._init_broker(settings)` 為 adapter 的建構入口。

## 注意事項
- 新增公開方法時請在抽象介面上提供 default 或 `abstractmethod`，**兩種子類都要支援**。
- callback 失敗一律 swallow（已內建 `try/except`），避免一個訂閱者壞掉影響其他。
- 不要直接從外部讀 `_fill_subs / _order_subs`；用 `dispatch_*`。
