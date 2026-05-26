# Skill：`RecordingWriter`（盤中行情錄製）

## 檔案位置
- `build_win/src/broker/recording.py`

## 主要職責
- Phase 1：把 SDK 推送的原始訊息與解析後的 `TickEvent / BookEvent` 寫成 gzip-NDJSON。
- 用背景 thread + bounded Queue，避免阻塞 SDK callback / engine 主流程。
- queue 滿時優先丟棄 `raw`，保留結構化資料。
- 主程式結束時 `close()` flush 殘餘訊息並寫入 `meta.json` 統計。

## 檔案結構
```
<out_root>/<YYYYMMDD>/session_<HHMMSS>.ticks.ndjson.gz
<out_root>/<YYYYMMDD>/session_<HHMMSS>.meta.json
```

## 主要 API
| 方法 | 用途 |
|------|------|
| `__init__(out_root, queue_size=20000, log_cb=None)` | 預備（不開檔） |
| `start(meta=None) -> Path` | 開檔、啟動 writer thread；回傳 session 目錄 |
| `write_raw(msg)` | 寫 SDK 原始訊息（queue 滿時可被丟棄） |
| `write_tick(ev: TickEvent)` | 寫 tick |
| `write_book(ev: BookEvent)` | 寫 book |
| `close()` | flush 殘餘訊息、寫 `meta.json`、停 thread |
| `cleanup_old_recordings(root, keep_days)` | 對 `<root>/<YYYYMMDD>` 目錄清除超齡 |
| `default_recording_root()` | 預設根目錄（exe 或 build_win 同層的 `log/recordings/`） |

## 與其他模組關係
- `gui.App._maybe_attach_recorder(cfg, feed, symbol_infos)` 在策略啟動時呼叫 `start()` 與 `FubonRealtimeFeed.attach_recorder(writer, record_raw=cfg.recording_record_raw)`。
- 設定欄位：`TradingConfig.recording_enabled / recording_dir / recording_keep_days / recording_record_raw`。
- 分析工具：`build_win/src/analyze_limitup_logs.py` 讀取 `session_*.ticks.ndjson.gz`。

## Side Effect
- 建立 `<root>/<YYYYMMDD>/` 目錄。
- 啟動 daemon thread `recording-writer`。
- 寫入 gzip 與 JSON 檔。

## 注意事項
- queue 上限預設 20000；不可低於 1000。
- `start()` 已 running 時，立即回現有 session 目錄（idempotent）。
- 例外處理：所有 `write_*` 必須 swallow（呼叫端不應因錄製失敗中斷）。
- `meta.json` 統計：`raw_count / tick_count / book_count / dropped_count / start_ts / end_ts`。
