---
name: feature-f13-daily-max-trades
description: >-
  **策略功能技能 F13** — 限制當日最大成交檔數，防止過度交易。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F13 — 每日最大成交檔數

## 1. 功能描述
當日累計已成交（進場成功）的股票檔數達到上限後，不再開新倉。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f13_enabled` | bool | True | 主開關 |
| `daily_max_trades` | int | 5 | 當日最多進場成功幾檔 |

## 3. 程式碼位置
- [engine.py](../../build_win/src/engine.py) `_tick()` 進場分支
- 計數來源：`self._daily_trade_count`（在 `_on_fill` 進場成交時 +1）

## 4. 邏輯
```python
if cfg.f13_enabled and self._daily_trade_count >= cfg.daily_max_trades:
    return
```

## 5. 注意事項
- **計算單位**：以「成交一筆進場」為一檔，同一股票多次出場再進場仍只計一次（看實作細節，目前是每次進場 +1，需依規格決定是否去重）。
- **跨日不重啟**：`_daily_trade_count` 不會自動 reset，需日終重置（建議 `08:50`）。

## 6. 與 F10 的命名混淆
**注意**：使用者口頭描述的「漲停消化量達 N 張就進場（與 F1 互斥）」**不是** `f13`。
- 目前 F13 = 「當日成交檔數上限」。
- 「消化量進場」尚未實作；建議新增獨立開關 `f_consume_enabled` / `consume_qty_threshold`。
