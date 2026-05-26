# Skill：盤中錄製分析工具 `analyze_limitup_logs.py`

## 檔案位置
- `build_win/src/analyze_limitup_logs.py`

## 用途
- 讀取 `RecordingWriter` 產生的 `session_*.ticks.ndjson.gz` 與對應 `*.meta.json`，回推每種鎖漲停候選邏輯的觸發時間。
- 用於：
  - 比較不同 `limit_up_detection_mode` 的判斷時機差異。
  - 驗證新增 / 修改的模式是否合預期。

## 使用方式
```bash
python3 analyze_limitup_logs.py <session_ticks.ndjson.gz> [--code 2330]
```

- 預設處理 meta 內所有 `symbol_universe` 的代碼；`--code` 可只看單一檔。

## 內部結構
- `SymbolState`：逐檔追蹤 `limit_up / last_price / trade_bid/ask / ask0 / bid0 / has_ask_levels / has_bid_levels`、各模式的「最早為 True 的時間」與「累積為 True 的次數」。
- 對每筆 tick / book：
  1. 更新 SymbolState 對應欄位。
  2. 呼叫 `limitup_detection.evaluate_limit_up_state(...)`。
  3. 對 `candidates` 內每個模式：若這次為 True 而上次為 False → 記錄「首次觸發」時間。

## 輸出
- 對每檔逐一印出：
  - 每個 mode 第一次為 True 的時間 / 累積為 True 的次數。
  - 每個 signal 首次為 True 的時間。

## 注意事項
- 與正式策略邏輯相依：模式名稱、訊號名稱必須與 `limitup_detection` 一致；新增模式 / 訊號時請同步更新此腳本的解析。
- 不依賴 PyQt / SDK，可在純 Python 環境執行。
- 大檔案分析需要時間，建議先用 `--code` 過濾單一標的迭代。
