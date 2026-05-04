---
name: feature-f4-limit-open-exit
description: >-
  **策略功能技能 F4** — 持倉中委買漲停板被打開即市價出場。
  使用時機：修改 F4 容忍檔位 / 容忍秒數、處理隔日庫存誤賣、調整出場下單策略。
  不適用：爆量出場（看 F5）。
applyTo:
  - "build_win/src/engine.py"
  - "build_win/src/config.py"
---

# F4 — 漲停打開即市價出場

## 1. 功能描述
持有部位期間，若該股的最佳委賣價不再等於漲停價（板被打開），立即以市價賣出。

## 2. 設定欄位
| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `f4_enabled` | bool | True | 主開關 |

> **目前無容忍度設定**。建議新增（見 §5）。

## 3. 程式碼位置
- 出場判斷：[engine.py](../../build_win/src/engine.py) `_tick()` 內 `if state.position_qty > 0:` 區段
- 漲停判斷來源：`StockState.is_at_limit_up`（由 `_on_book` 維護：`ask0_price == limit_up`）

## 4. 決策邏輯
```python
if state.position_qty > 0:
    if cfg.f4_enabled and not state.is_at_limit_up and state.last_price is not None:
        reason = "委買漲停，市場打開，市價出場"
        self._do_sell(state, state.position_qty, reason)
```

## 5. ⚠️ 已知風險（高優先級）

### 5-1 隔日庫存誤賣
跨日不重啟程式時，若隔天該股**今日尚未到過漲停**，`is_at_limit_up = False` → F4 立即觸發 → 隔日庫存被市價賣出。

**修法建議**（新增「當日曾達漲停」前提）：
```python
has_been_at_limit = state.candle_index > 0 or state.entry_price is not None
if (cfg.f4_enabled and has_been_at_limit
        and not state.is_at_limit_up and state.last_price is not None):
    ...
```

> 目前實際因 engine 不會自動接管隔日帳戶庫存（只 GUI 顯示），bug 暫時被掩蓋；補了上述條件才是治本。

### 5-2 瞬間打開又封回（洗盤）
板被吃開 1 檔後立刻補回，仍會在打開那一瞬間被殺出。
**建議新增**：
| 欄位 | 預設 | 說明 |
|---|---|---|
| `f4_tolerance_ticks` | 0 | ask\[0] 距漲停 ≤N 檔仍視為漲停 |
| `f4_open_seconds` | 0.0 | 板打開持續 ≥N 秒才賣 |

## 6. 與其他功能互動
- F4 / F5 同時 enabled 時，F5 先檢查（爆量優先）；任一觸發即出場後 return。
- 完全不影響 F12（封鎖規則）；但出場後 `state.sold_today = True`，會餵 F12。

## 7. 測試
- `tests/test_orders.py` — 模擬 ask\[0] 跌離漲停的 BookEvent，斷言觸發 SELL。
