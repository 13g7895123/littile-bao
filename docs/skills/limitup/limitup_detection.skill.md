# Skill：鎖漲停判斷工具 `limitup_detection`

## 檔案位置
- `build_win/src/limitup_detection.py`

## 主要職責
- 提供 10 種「鎖板 / 觸板候選邏輯」的命名集 `LIMIT_UP_DETECTION_MODES`。
- 提供 `evaluate_limit_up_state(...)` 將即時行情數值轉成各候選模式的 bool 結果。
- 提供 `resolve_limit_up_mode(mode)`：把字串解析為合法模式，缺省回 `DEFAULT_LIMIT_UP_DETECTION_MODE`。

## 模式清單
| 模式 key | 中文敘述 |
|----------|----------|
| `ask_or_bid_or_last` | ask1=漲停 或 bid1=漲停 或 最新成交=漲停 |
| `ask_only` | 只有 ask1=漲停 才算封板 |
| `bid_only` | 只有 bid1=漲停 才算鎖板 |
| `bid_or_trade_flag` | bid1=漲停 或 API 的 isLimitUpBid=true |
| `bid_and_last` | bid1=漲停 且 最新成交=漲停 |
| `bid_and_no_ask` | bid1=漲停 且 沒有任何委賣檔 |
| `bid_and_zero_ask` | bid1=漲停 且 沒有委賣或賣一量=0 |
| `strict_lock_from_user_rule` | **預設**；isLimitUpPrice=true 且 bid1 漲停且有量，且 (無委賣 / 賣一量=0 / 賣一高於漲停) |
| `trade_price_only` | 只有最新成交=漲停 |
| `trade_flag_only` | 只有 API 漲停旗標為真 |

## 主要 API
- `evaluate_limit_up_state(*, limit_up, ask0_price, ask0_volume, bid0_price, bid0_volume, last_price, trade_bid=None, trade_ask=None, has_ask_levels=False, has_bid_levels=False, is_limit_up_price=None, is_limit_up_bid=None, is_limit_up_ask=None) -> dict`
  - 回傳結構：
    ```python
    {
      "ask_qty_at_limit": int,   # 漲停價委賣張數（不為漲停時 0）
      "signals": {...bool...},   # 每個基本訊號的真假
      "candidates": {mode: bool} # 每個模式的判斷結果
    }
    ```
- `resolve_limit_up_mode(mode: str) -> str`：合法 → 原樣回；非法或空 → 預設模式。

## 與其他模組關係
- 被 `engine._refresh_limit_up_state` 呼叫，產生 `state.limit_up_signal_states / limit_up_candidate_states`。
- GUI 的「鎖板測試頁籤」會顯示這些 signals / candidates，並可即時切換 `active_limit_up_mode`。
- 設定值名稱與 `TradingConfig.limit_up_detection_mode` 對齊；GUI 下拉選單由 `_populate_limit_up_mode_combo` 寫入。

## 注意事項
- 新增模式時：
  1. 在 `LIMIT_UP_DETECTION_MODES` 加上 `key: 中文描述`。
  2. 在 `evaluate_limit_up_state.candidates` 字典加上對應布林表達式。
  3. **檢查 `TradingConfig.from_dict` 是否需要把舊值升級到新預設**。
  4. GUI 的下拉會自動取自 `LIMIT_UP_DETECTION_MODES`，無需另外硬寫。
- 數值一律先轉 `Decimal`，避免 float 比較誤差。

## 對應測試
- 由 `engine` 與 `gui` 相關測試間接驗證；新增模式建議補單元測試於 `tests/` 下。
