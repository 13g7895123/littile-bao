---
name: feature-f5-volume-spike-exit
description: >-
  **策略功能技能 F5** — 持倉中 1 秒成交量 > 門檻就市價賣出。
  使用時機：調整 `volume_spike_sell_threshold`、修改 1 秒成交量計算窗口。
  不適用：委託排隊中的取消（看 F6）。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F5 — 持倉爆量出場

## 1. 功能描述
持有部位時，若最近 1 秒累計成交量 > 設定值，視為主力出貨／爆量殺尾，立即市價賣出。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f5_enabled` | bool | True | 主開關 |
| `volume_spike_sell_threshold` | int | 499 | 1 秒成交張數門檻（>） |

## 3. 程式碼位置
- 觸發點：[engine.py](../../build_win/src/engine.py) `_tick()` 持倉分支
- 1 秒成交量來源：`StockState.last_1s_vol`，由 `_on_tick` 維護 `tick_vols` deque（保留近 1 秒）

## 4. 邏輯
```python
if state.position_qty > 0:
    if cfg.f5_enabled and state.last_1s_vol > cfg.volume_spike_sell_threshold:
        reason = f"1秒成交量爆量({state.last_1s_vol})，市價出場"
        self._do_sell(state, state.position_qty, reason)
        return
```

## 5. 注意事項
- **單位是「張」**（1 張 = 1000 股）。SDK 推播若是股數，需先 `vol // 1000`，目前 RealtimeFeed 已轉換。
- **窗口是「滾動 1 秒」**：`tick_vols` 內保留 `now - 1.0s` 之後的資料；非「整秒對齊」。
- 與 F4 順序：建議 F5 先檢，再 F4，避免漲停剛打開就先被 F5 蓋過。
