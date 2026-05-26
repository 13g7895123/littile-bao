# broker 套件

> 富邦 Neo SDK 與內部各模組之間的「適配層」。`engine` 與 `gui` 都只透過此層存取券商，不直接依賴 SDK。

## 子模組總覽

| 子模組 | 程式碼 | skill |
|--------|--------|-------|
| Adapter（連線生命週期 / 帳號） | `broker/adapter.py` | [`adapter/`](./adapter/) |
| Realtime（行情訂閱） | `broker/realtime.py` | [`realtime/`](./realtime/) |
| Orders（下單 / Dry-Run / Mock） | `broker/orders.py` | [`orders/`](./orders/) |
| Account（庫存 / 帳務 polling） | `broker/account.py` | [`account/`](./account/) |
| Universe（選股 / 個股基本資料） | `broker/universe.py` | [`universe/`](./universe/) |
| Recording（盤中錄製） | `broker/recording.py` | [`recording/`](./recording/) |
| Models / Errors / Fees | `broker/{models,errors,fees}.py` | [`models_errors_fees.skill.md`](./models_errors_fees.skill.md) |

## 對外公開的 API
所有公開符號統一由 `broker/__init__.py` 匯出（見其 `__all__`）。引用時請寫：
```python
from broker import FubonAdapter, MockAdapter, OrderRequest, ...
```
**請勿**直接 `from broker.adapter import ...`，除非有強烈理由（例如測試）。
