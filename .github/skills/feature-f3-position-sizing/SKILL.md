---
name: feature-f3-position-sizing
description: >-
  **策略功能技能 F3** — 每檔投入金額換算進場張數。
  使用時機：調整 `per_stock_amount`、修改張數計算公式、處理零股 / 不足一張情境。
  不適用：總曝險上限（看 F13 daily_max_trades）。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F3 — 每檔投入金額 → 張數換算

## 1. 功能描述
依使用者設定的「每檔投入金額」與漲停價自動換算下單張數，避免高價股壓爆資金。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `per_stock_amount` | int | 100,000 | 每檔投入金額（TWD） |

## 3. 程式碼位置
- 進場下單前換算：[engine.py](../../build_win/src/engine.py) `_tick()` 進場分支
- 公式：
  ```python
  qty = max(1, int(cfg.per_stock_amount // (limit_up * 1000)))
  ```

## 4. 注意事項
- **最低 1 張**：金額不足以買 1 張時仍下 1 張，避免整檔被略過。若不希望，需在 engine 增加「< 1 張則 skip」分支。
- **零股不支援**：張數一律為整數張。
- **手續費 / 證交稅未從 `per_stock_amount` 扣除**：實際成本會略高，建議預留 0.5% 緩衝。

## 5. 與其他功能互動
- F9 (`price_min` / `price_max`) 限制了股價區間，配合 F3 可避免「一檔買不到 1 張」的尷尬。
