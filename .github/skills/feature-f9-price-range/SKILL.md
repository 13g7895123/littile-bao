---
name: feature-f9-price-range
description: >-
  **策略功能技能 F9** — 股價區間篩選（避免雞蛋水餃股 / 過高股）。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F9 — 股價區間

## 1. 功能描述
僅交易現價在 `[price_min, price_max]` 區間內的股票。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f9_enabled` | bool | True | 主開關 |
| `price_min` | float | 10.0 | 下限（含） |
| `price_max` | float | 500.0 | 上限（含） |

## 3. 程式碼位置
- [engine.py](../../build_win/src/engine.py) `_tick()` 最早期的篩選分支
- 比較對象：`info.limit_up`（不是 `last_price`，避免無 tick 時漏判）

## 4. 邏輯
```python
if cfg.f9_enabled:
    if info.limit_up < cfg.price_min or info.limit_up > cfg.price_max:
        return
```

## 5. 注意事項
- **以漲停價作為比較基準**：可在開盤前就過濾，與 last_price 是否到位無關。
- 若想以「現價」而非「漲停價」判斷，需把比較對象改為 `state.last_price` 並處理 None。
- 與 F3 (`per_stock_amount`) 搭配：高價股容易被 F3 卡到不足 1 張，搭配 `price_max` 可預先排除。
