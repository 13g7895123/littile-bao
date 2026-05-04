---
name: feature-f2-market-filter
description: >-
  **策略功能技能 F2** — 上市（TSE）/ 上櫃（OTC）市場選擇。
  使用時機：選股清單載入、`scan_daily()` 篩選範圍、GUI 市場 checkbox 行為。
  不適用：個股屬性過濾（處置/注意股，看 F11）。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
  - "build_win/src/broker/universe.py"
  - "build_win/src/gui.py"
---

# F2 — 市場別選擇（TSE / OTC）

## 1. 功能描述
決定「漲停候選股票池」是否包含上市、上櫃。可同時勾選；至少需勾一項。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `market_twse` | bool | True | 上市 |
| `market_tpex` | bool | True | 上櫃 |

輔助方法：`TradingConfig.get_markets() -> ["TSE", "OTC"]`。

## 3. 程式碼位置
- 設定彙整：[config.py](../../build_win/src/config.py) `get_markets()`
- 套用範圍：[broker/universe.py](../../build_win/src/broker/universe.py) `scan_daily(markets=...)`
- GUI：[gui.py](../../build_win/src/gui.py) 市場兩個 QCheckBox

## 4. 邏輯
universe scan 時依 `markets` 過濾 SDK 回傳清單；engine 不再對個股二次篩 market。

## 5. 注意事項
- **兩者皆未勾**：`get_markets()` 回傳空 list，將造成 universe 空集合 → 無交易；GUI 應禁止全部取消。
- 興櫃、零股、ETF 等不在範圍內。
