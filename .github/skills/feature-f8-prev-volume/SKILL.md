---
name: feature-f8-prev-volume
description: >-
  **策略功能技能 F8** — 前一日成交量門檻（流動性篩選）。
  使用時機：universe `scan_daily()` 流動性過濾、調整 `daily_volume_min`、
  決定是否在 engine 內也加二次防護。
applyTo:
  - "build_win/src/broker/universe.py"
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F8 — 昨日成交量篩選

## 1. 功能描述
過濾流動性過低的股票（容易拉不上漲停或出不掉）。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f8_enabled` | bool | True | 主開關 |
| `daily_volume_min` | int | 500 | 昨日成交「張數」門檻（≥） |

## 3. 程式碼位置
- 選股階段：[broker/universe.py](../../build_win/src/broker/universe.py) `scan_daily(min_prev_volume=...)`
- engine 內：⚠️ **目前 `_tick()` 沒有讀取 `f8_enabled`**，僅 universe 過濾一次。

## 4. 已知差距
若需要在 engine 也做防護（避免使用者手動把股票加入但忘了流動性），可：
```python
prev_vol_lots = info.prev_volume // 1000     # 假設 prev_volume 為股數
if cfg.f8_enabled and prev_vol_lots < cfg.daily_volume_min:
    return
```
需先確認 `StockInfo.prev_volume` 欄位是否存在（目前未定義）。

## 5. 注意事項
- 單位 = 張（1 張 = 1000 股）。
- 「昨日」 = 上一個交易日；連假後第一個交易日仍以最近一個交易日為準。
