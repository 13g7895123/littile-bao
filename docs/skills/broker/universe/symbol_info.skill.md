# Skill：`SymbolInfo` + 漲跌停 / 選股工具

## 檔案位置
- `build_win/src/broker/universe.py`

## 主要 DTO
- `SymbolInfo`：開盤前 / 收盤後一次性載入的個股基本資料。
  - 核心：`code, name, market(TSE/OTC), prev_close, quote_price, limit_up_price, limit_down_price`
  - 衍生：`prev_volume, is_disposal, is_attention, is_day_trade_restricted`
  - 漲停推估：`open_limit_up, prior_limit_up_streak(昨日起連續收漲停天數), closed_at_limit_up`
  - 顯示：`display_prev_close`（UI 比較基準；不影響策略）

## 漲跌停 / Tick 工具
| 函式 | 用途 |
|------|------|
| `tick_size(price) -> Decimal` | 依台股 tick 表回傳 tick |
| `round_to_tick(price, mode="down"/"up"/"near") -> Decimal` | 將價格 round 到 tick 倍數 |
| `calc_limit_up(prev_close) -> Decimal` | 昨收 ×1.1 → 依 tick 無條件捨去 |
| `calc_limit_down(prev_close) -> Decimal` | 昨收 ×0.9 → 依 tick 無條件進位 |
| `is_limit_up_close(close, prev_close) -> bool` | 該日收盤是否為前一日推算漲停價 |
| `next_session_prior_limit_up_streak(info) -> Optional[int]` | 推估隔日開盤前的連續漲停日數 |
| `build_next_session_symbol_info(info)` | 收盤快照 → 隔日選股用 `SymbolInfo` |
| `build_symbol_info(code, name, market, prev_close, *, ...)` | 由昨收計算漲跌停並包成 `SymbolInfo` |

## Tick 表
| 價格上限 | tick |
|----------|------|
| < 10     | 0.01 |
| < 50     | 0.05 |
| < 100    | 0.1  |
| < 500    | 0.5  |
| < 1000   | 1    |
| ≥ 1000   | 5    |

## 注意事項
- 漲跌停一律以 `Decimal` 比較，避免浮點誤差。
- 修改 tick 表需同步檢查 `engine` 中 `_tick_size` 行為。
- `SymbolInfo` 新增欄位請保留 dataclass 預設值並更新 `build_symbol_info()`。
