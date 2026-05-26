# Skill：帳戶服務 `AccountService` 系列

## 檔案位置
- `build_win/src/broker/account.py`

## DTO
- `Position(code, name, qty, avg_cost, last_price=0, market_value=0, unrealized_pnl=0, unrealized_pnl_pct=0)`
- `AccountSnapshot(cash=0, buying_power=0, today_realized_pnl=0, total_unrealized_pnl=0, positions=[], updated_at=now)`
- `SnapshotCallback = Callable[[AccountSnapshot], None]`

## 抽象介面
```python
class AccountService(ABC):
    @abstractmethod
    def snapshot(self) -> AccountSnapshot: ...
    def start_polling(self, callback, interval=10.0) -> None: ...
    def stop(self) -> None: ...
```

- `start_polling`：開背景 thread，每 `interval` 秒呼叫 `snapshot()` 並回呼。
- `stop`：設定 `_poll_stop` event。

## `MockAccountService`
- `__init__(initial_cash=Decimal("1000000"))`
- `set_positions(positions)`：由 `MockAdapter._sync_mock_account` 在收到成交後注入。
- `snapshot()`：用本地 `_cash` + `_positions` 推估市值與未實現損益。

## `FubonAccountService`
- 接 `FubonAdapter`，登入後可呼叫：
  - `sdk.stock.inventories(account)` → 解析成 `List[Position]`。
  - `sdk.accounting.bank_remain(account)` → `cash / buying_power`。
- 任一 SDK 呼叫失敗時 swallow，並讓 `snapshot` 仍能回部分資料。

## 與其他模組關係
- `BrokerAdapter.account_service()` 是工廠入口（Mock / Fubon 各自 lazy init）。
- `gui.App._on_account_snapshot` 透過 `start_polling` 接收快照並更新「庫存 / 損益 / 買進力」UI。
- 庫存單位換算：SDK `today_qty` 為股數，這裡會轉成「張」（除以 1000）。

## 注意事項
- polling 間隔不要設太短（建議 ≥ 5 秒）以免打爆 SDK。
- 新增帳務欄位：先更新 `AccountSnapshot`，再分別實作 Mock / Fubon。
- 計算 `unrealized_pnl_pct` 時，`avg_cost=0` 會回傳 0 避免除零。

## 對應測試
- `build_win/src/tests/test_account.py`
