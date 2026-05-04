# 策略功能技能索引

本目錄收錄 13 條策略功能（F1–F13）對應的技能文件，提供 Copilot 在修改 [build_win/src/engine.py](../../build_win/src/engine.py) / [build_win/src/config.py](../../build_win/src/config.py) / [build_win/src/gui.py](../../build_win/src/gui.py) 時自動載入背景知識。

| 編號 | 技能 | 主題 |
|---|---|---|
| F1  | [feature-f1-entry-time-window](feature-f1-entry-time-window/SKILL.md) | 進場時段 × 委賣張數門檻 |
| F2  | [feature-f2-market-filter](feature-f2-market-filter/SKILL.md) | 上市 / 上櫃市場別 |
| F3  | [feature-f3-position-sizing](feature-f3-position-sizing/SKILL.md) | 每檔投入金額換算張數 |
| F4  | [feature-f4-limit-open-exit](feature-f4-limit-open-exit/SKILL.md) | 漲停打開即市價出場 |
| F5  | [feature-f5-volume-spike-exit](feature-f5-volume-spike-exit/SKILL.md) | 持倉爆量出場 |
| F6  | [feature-f6-volume-spike-cancel](feature-f6-volume-spike-cancel/SKILL.md) | 排隊中爆量取消 |
| F7  | [feature-f7-candle-limit](feature-f7-candle-limit/SKILL.md) | K 棒序號限制 |
| F8  | [feature-f8-prev-volume](feature-f8-prev-volume/SKILL.md) | 昨日成交量篩選 |
| F9  | [feature-f9-price-range](feature-f9-price-range/SKILL.md) | 股價區間 |
| F10 | [feature-f10-ask-volume-confirm](feature-f10-ask-volume-confirm/SKILL.md) | 委賣價 + 即時量雙重確認 |
| F11 | [feature-f11-special-stock-filter](feature-f11-special-stock-filter/SKILL.md) | 排除處置 / 注意 / 限當沖股 |
| F12 | [feature-f12-open-limitup-block](feature-f12-open-limitup-block/SKILL.md) | 開盤即漲停封鎖 |
| F13 | [feature-f13-daily-max-trades](feature-f13-daily-max-trades/SKILL.md) | 當日最大成交檔數 |

## 領域技能
| 技能 | 主題 |
|---|---|
| [stock-order-api](stock-order-api/SKILL.md) | Fubon Neo 串接（下單 / 帳務 / 行情） |

## 關聯文件
- 邏輯衝突分析：[策略邏輯問題分析.md](../../策略邏輯問題分析.md)
- 儀表板需求：[儀表板串接需求說明.md](../../儀表板串接需求說明.md)
