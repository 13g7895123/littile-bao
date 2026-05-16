---
name: feature-f11-special-stock-filter
description: >-
  **策略功能技能 F11** — 排除處置股 / 注意股 / 限當沖股。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
  - "build_win/src/broker/universe.py"
---

# F11 — 特殊股排除

## 1. 功能描述
為避免高風險或交易限制，排除：
- 處置股 (`is_disposal`)
- 注意股 (`is_attention`)
- 限當沖股 (`is_day_trade_restricted`)

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f11_enabled` | bool | True | 一鍵排除三類 |

> 目前**沒有「分類獨立開關」**；若想保留注意股、僅排除處置股，需擴充欄位。

## 3. 程式碼位置
- [engine.py](../../build_win/src/engine.py) `_tick()` 下單前最後確認
- [gui.py](../../build_win/src/gui.py) `_load_trading_runtime()` 候選股篩完後批次確認
- 標記來源：[broker/universe.py](../../build_win/src/broker/universe.py) 抓取 SDK metadata 後寫入 `StockInfo`

## 4. 邏輯
```python
候選股先完成價格 / 量 / K 棒等篩選
若仍有交易 quota 且 F11 開啟，才用富邦 API 批次刷新特殊股旗標
引擎下單前再以單檔 API 結果做最後防線；確認失敗或命中特殊股就不買
```

## 5. 注意事項
- SDK 屬性可能盤中變化（例如盤中被列為注意股）：策略啟動會做候選股批次確認，實際下單前還會再確認單檔。
- 富邦 API 未回傳候選股特殊旗標時採保守排除，避免未確認就下單。
- 黑名單（`config.blacklist`）功能獨立於 F11，於 universe 階段過濾。
