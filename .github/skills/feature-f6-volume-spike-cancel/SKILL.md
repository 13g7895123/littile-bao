---
name: feature-f6-volume-spike-cancel
description: >-
  **策略功能技能 F6** — 委託排隊中遇 1 秒爆量則取消委託。
  使用時機：調整 `volume_spike_cancel_threshold`、修改取消後是否封鎖再進場。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F6 — 排隊中爆量取消

## 1. 功能描述
進場委託送出後尚未成交（pending=True）時，若最近 1 秒成交量 > 門檻，主動 cancel 該筆委託，並把該股「當日封鎖」（`entry_blocked=True`）避免反覆掛單。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f6_enabled` | bool | True | 主開關 |
| `volume_spike_cancel_threshold` | int | 499 | 1 秒成交張數門檻（>） |

## 3. 程式碼位置
- 觸發點：[engine.py](../../build_win/src/engine.py) `_tick()` 開頭（早於 F4/F5 出場分支）
- 取消委託：`self._do_cancel(state, ...)`

## 4. 邏輯
```python
if state.pending and cfg.f6_enabled \
   and state.last_1s_vol > cfg.volume_spike_cancel_threshold:
    self._do_cancel(state, "排隊中1秒爆量，取消委託")
    state.entry_blocked = True
```

## 5. 注意事項
- **取消後同日不再進場**：靠 `entry_blocked` 旗標；跨日不重啟仍 True，需日終 reset。
- F5 與 F6 共用 `last_1s_vol`，差別在於 `pending` vs `position_qty > 0`。
- 若委託在門檻觸發前已部分成交，部分成交量不會被 F6 撤掉，後續走 F4/F5 出場。
