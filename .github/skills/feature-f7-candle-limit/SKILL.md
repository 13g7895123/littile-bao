---
name: feature-f7-candle-limit
description: >-
  **策略功能技能 F7** — 只買起漲後第幾根 K 棒以內。
  使用時機：調整 `candle_limit`、修改起漲 K 棒計算規則、與 F1/F10 進場條件互動。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F7 — K 棒序號限制

## 1. 功能描述
僅在「該股第一次到達漲停」之後的前 N 根 1 分鐘 K 棒內進場。預設只買第 1、第 2 根。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f7_enabled` | bool | True | 主開關 |
| `candle_limit` | int | 2 | K 棒序號上限（含） |

## 3. 程式碼位置
- 進場判斷：[engine.py](../../build_win/src/engine.py) `_tick()`
- `candle_index` 維護：`_on_book` 內偵測首次 `is_at_limit_up=True` 時設 `limit_up_since`，依分鐘累加 `candle_index`

## 4. 邏輯
```python
if cfg.f7_enabled and state.candle_index > cfg.candle_limit:
    return
# candle_index == 0：尚未到過漲停，不允許進場
if state.candle_index == 0:
    return
```

## 5. 注意事項
- `candle_index` 從 1 開始（第一根 = 1）。
- **跨日不重啟** `candle_index` 不會 reset → 隔日值偏高可能被 F7 擋掉。日終 reset 必加。
- 若一檔股票今天先漲停又打開又再漲停，`candle_index` 是「自第一次漲停起累計」，不是「自最後一次起漲」。
