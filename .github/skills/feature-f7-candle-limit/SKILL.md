---
name: feature-f7-candle-limit
description: >-
  **策略功能技能 F7** — 只買日 K 連續漲停第幾根以內。
  使用時機：調整 `candle_limit`、修改日 K 起漲序號計算規則、與 F1/F10 進場條件互動。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F7 — 日 K 連續漲停序號限制

## 1. 功能描述
僅在「日 K 連續漲停序號」前 N 根內進場。預設只買第 1、第 2 根。

定義：昨天沒有收漲停、今天第一次觸及漲停 = 第 1 根；昨天已收漲停、今天再次觸及漲停 = 第 2 根。盤中同一天開板又封回不會增加根數。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f7_enabled` | bool | True | 主開關 |
| `candle_limit` | int | 2 | 日 K 連續漲停序號上限（含） |

## 3. 程式碼位置
- 進場判斷：[engine.py](../../build_win/src/engine.py) `_tick()`
- `candle_index` 維護：`engine.py` `_mark_limit_up_touched()` 在今天首次觸及漲停時設為 `prior_limit_up_streak + 1`
- 昨日前連續漲停日 K 資料：`broker/universe.py` `SymbolInfo.prior_limit_up_streak`

## 4. 邏輯
```python
if cfg.f7_enabled and state.candle_index > cfg.candle_limit:
    return
# candle_index == 0：尚未到過漲停，不允許進場
if state.candle_index == 0:
    return
```

## 5. 注意事項
- `candle_index` 從 1 開始（第一根 = 1），且是日 K，不是 1 分鐘 K。
- **跨日不重啟** `candle_index` 不會 reset → 隔日值偏高可能被 F7 擋掉。日終 reset 必加。
- 若一檔股票今天先漲停又打開又再漲停，`candle_index` 仍維持今天的日 K 序號，不會因盤中反覆封板增加。
