---
name: feature-f10-ask-volume-confirm
description: >-
  **策略功能技能 F10** — 委賣價比例 + 即時量雙重確認進場。
  使用時機：調整 `ask_price_ratio` / `entry_volume_confirm`、設計 F1/F10 互斥邏輯。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F10 — 委賣價 × 即時量雙重確認

## 1. 功能描述
進場前確認：
1. 最佳委賣價已 ≥ 漲停價 × `ask_price_ratio`（預設 1.0 = 必須等於漲停）。
2. 最近 1 秒成交量 ≥ `entry_volume_confirm`（確認有人正在吃貨）。

避免「委賣張數雖少但其實沒人在買」的假象。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f10_enabled` | bool | True | 主開關 |
| `ask_price_ratio` | float | 1.0 | 委賣價 / 漲停價 下限 |
| `entry_volume_confirm` | int | 50 | 1 秒成交張數下限（≥） |

## 3. 程式碼位置
- [engine.py](../../build_win/src/engine.py) `_tick()` 進場最末一段

## 4. 邏輯
```python
if cfg.f10_enabled:
    if state.ask0_price is None or state.ask0_price < info.limit_up * cfg.ask_price_ratio:
        return
    if state.last_1s_vol < cfg.entry_volume_confirm:
        return
```

## 5. ⚠️ 與 F1 邏輯衝突

| 條件 | F1 期望 | F10 期望 |
|---|---|---|
| 委賣張數 | **少**（< `ask_queue_threshold`） | — |
| 1 秒成交量 | — | **多**（≥ `entry_volume_confirm`） |

兩者並非必然衝突，但使用者通常擇一啟用：
- 早盤搶漲停 → 開 F1，關 F10。
- 漲停消化量進場 → 開 F10，關 F1。

**建議**：新增 `f1_f10_exclusive: bool = True`，啟動時若兩者皆 enabled 就警告並選擇優先策略。
