---
name: feature-f12-open-limitup-block
description: >-
  **策略功能技能 F12** — 開盤即漲停 + 當日已賣過 = 封鎖再進場。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F12 — 開盤即漲停且已賣過則封鎖

## 1. 功能描述
若該股「開盤即漲停」且當天已被本系統賣出過一次，就不再進場（避免追高再砸）。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f12_enabled` | bool | True | 主開關 |

## 3. 程式碼位置
- [engine.py](../../build_win/src/engine.py) `_tick()` 進場分支
- 旗標來源：
  - `info.open_limit_up`：universe scan 階段判定
  - `state.sold_today`：`_do_sell` 完成時設為 True

## 4. 邏輯
```python
if cfg.f12_enabled and info.open_limit_up and state.sold_today:
    return
```

## 5. ⚠️ 重要邊界釐清
| 情境 | F12 是否封鎖 |
|---|---|
| 開盤即漲停 + 賣過 | ✅ 封鎖 |
| 開盤即漲停 + 未賣過 | ❌ 不封鎖（可進場） |
| 非開盤即漲停 + 賣過 | ❌ 不封鎖（**靠 `entry_blocked` 擋**） |
| 非開盤即漲停 + 未賣過 | ❌ 不封鎖 |

亦即：**普通漲停股賣出後，是靠 `entry_blocked` 阻止當日重買**；F12 只強化「開盤即漲停」這類最危險的情境。

## 6. 建議擴充
- `f12_skip_open_limit_up: bool = False`：是否「不論有無賣過，都跳過開盤即漲停」。
- 跨日不重啟需配合「日終 reset」清除 `sold_today` / `entry_blocked`。
