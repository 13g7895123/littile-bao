# Skill：`broker.models` / `broker.errors` / `broker.fees`

> 三個小檔合併為一份 skill，皆屬 broker 套件內的「基礎型別與公式」層。

---

## A. `broker.models` — 跨層 DTO

### 主要型別
| 類別 | 說明 |
|------|------|
| `ConnectionState` (Enum) | `DISCONNECTED / CONNECTING / CONNECTED / LOGIN_FAILED / ERROR` |
| `AccountRef` (frozen dataclass) | 歸戶帳號摘要；`branch_no / account_no / account_type / account_name`；`display` property |
| `LoginResult` | `success / accounts / selected / message` |
| `TickEvent` | 即時成交（含 `is_limit_up_price/bid/ask`、`is_trial`） |
| `BookLevel` | `price / volume` |
| `BookEvent` | `code / time / ask: List[BookLevel] / bid: List[BookLevel]` |
| `OrderSide` (Enum) | `BUY / SELL` |
| `OrderStatus` (Enum) | `PENDING / PARTIAL / FILLED / CANCELLED / REJECTED` |
| `OrderEvent` | 委託回報 DTO（含 `filled_qty / status / source`） |
| `FillEvent` | 成交回報 DTO |

### 設計守則
- 一律使用 `Decimal` 表示價格；`int` 表示張數（一張 1000 股）。
- DTO 不含 SDK 物件；如 SDK 回傳需轉換，請在 `adapter` 內做。
- 新增欄位時請保留向後相容（dataclass 預設值）。

---

## B. `broker.errors` — 例外階層

```
BrokerError
├── FubonAuthError          # 帳密 / API Key / 憑證驗證失敗
├── FubonNotLoggedInError   # 未登入即呼叫
├── FubonNetworkError       # WebSocket / HTTP 異常
├── FubonOrderError         # 下單失敗
└── FubonConfigError        # 設定欄位缺失 / 格式錯
```

- 所有 broker 內的失敗應拋出此階層子類，外層只需 `except BrokerError`。
- 引擎、GUI 收到 `FubonAuthError` 時可考慮降級為 `MockAdapter`。

---

## C. `broker.fees` — 手續費 / 證交稅 / 損益

### 常數
| 名稱 | 值 | 說明 |
|------|----|------|
| `FEE_RATE` | `Decimal("0.001425")` | 手續費率（買賣雙邊） |
| `FEE_DISCOUNT` | `Decimal("0.6")` | 預設 6 折（可調） |
| `MIN_FEE` | `Decimal("20")` | 最低手續費 |
| `TAX_RATE` | `Decimal("0.003")` | 證交稅率（賣出） |
| `TAX_RATE_DAYTRADE` | `Decimal("0.0015")` | 現股當沖證交稅減半 |

### 主要 API
- `calc_fee(price, qty_lots, discount=FEE_DISCOUNT) -> Decimal`
- `calc_tax(price, qty_lots, day_trade=False) -> Decimal`
- `realized_pnl(buy_price, sell_price, qty_lots, day_trade=False, fee_discount=FEE_DISCOUNT) -> TradePnL`
  - `TradePnL(gross, buy_fee, sell_fee, tax, net)`

### 注意事項
- 手續費以 `ROUND_DOWN` 截到整數，再套用 `MIN_FEE`。
- 計算單位：張 ×1000 股 × 價格。
- 引擎在 `_on_broker_fill` 中以 `realized_pnl` 統計當日已實現損益。

## 對應測試
- `build_win/src/tests/test_fees.py`
- 對 errors / models 通常由 broker 其他測試覆蓋。
