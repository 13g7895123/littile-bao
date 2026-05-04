---
name: feature-f1-entry-time-window
description: >-
  **策略功能技能 F1** — 「10 點前 + 委賣（漲停價）低於 N 張」進場條件。
  使用時機：調整 `entry_before_time` / `ask_queue_threshold`、修改進場時段邏輯、
  排查為何收盤前後仍有委託、與 F10/F13 互斥開關設計。
  不適用：出場條件（看 F4/F5）、選股清單篩選（看 universe）。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
  - "build_win/src/gui.py"
  - "build_win/src/tests/**"
---

# F1 — 進場時段 × 委賣張數門檻

## 1. 功能描述
僅在指定時間之前（預設 `10:00`）、且漲停價的「最佳委賣張數」低於門檻（預設 100 張）時才允許進場。早盤越接近漲停、賣壓越輕的個股越優先進場。

## 2. 設定欄位（[config.py](../../build_win/src/config.py)）
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f1_enabled` | bool | True | 主開關 |
| `entry_before_time` | str `"HH:MM"` | `"10:00"` | 進場截止時間（含等號則拒絕） |
| `ask_queue_threshold` | int | 100 | 漲停價最佳委賣張數上限（< 才進場） |

## 3. 程式碼位置
- 進場決策：[engine.py](../../build_win/src/engine.py) `_tick()` 內的 F1 區段
- 委賣張數來源：`StockState.ask_qty_at_limit`（由 `_on_book` 在 `ask0_price == limit_up` 時更新）
- GUI 綁定：[gui.py](../../build_win/src/gui.py) 設定分頁 F1 區塊

## 4. 決策邏輯
```python
if cfg.f1_enabled:
    cutoff = dtime(*map(int, cfg.entry_before_time.split(":")))
    if datetime.now().time() >= cutoff:
        return                            # 過了進場時段
    if state.ask_qty_at_limit >= cfg.ask_queue_threshold:
        return                            # 委賣張數過多
```

## 5. 已知衝突與限制
- **與 F10「委賣價 + 即時量雙重確認」目前是 AND 關係**：F1 要求委賣張數**少**，但 F10 的 `entry_volume_confirm` 要求 1 秒成交量**多**，使用者通常擇一啟用。建議新增 `f1_f10_exclusive` 開關或在 GUI 提示。
- **委賣張數定義**：必須是 `ask[0] == limit_up` 才有效；若已被打開（最佳委賣 < 漲停價）`ask_qty_at_limit = 0`，會自動讓 F1 通過 — 但此時 F4 立刻觸發出場，所以不會誤買。
- **時間格式**：僅支援 `HH:MM`，不支援秒。

## 6. 測試入口
- `tests/test_orders.py`、`tests/test_realtime.py`（驗證委賣張數推播）
- 手動：[engine.py](../../build_win/src/engine.py) Mock 行情啟動。

## 7. 常見問題
- **「100 張內買到，剩 50 張掛賣，會被 F4 賣？」** → 不會。F4 看 `is_at_limit_up`（仍 True），與 F1 已通過後的張數無關。詳見[策略邏輯問題分析.md](../../策略邏輯問題分析.md)。
