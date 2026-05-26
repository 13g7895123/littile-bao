# Skill：執行時 Logging `app_logging`

## 檔案位置
- `build_win/src/app_logging.py`

## 主要職責
- 把程式中的 `print` / `sys.stderr` / 未捕捉例外集中寫入實體檔。
- 過濾掉富邦 SDK / WebSocket 雜訊（如 `tungstenite::`、`sdk_core::`、`trying to connect to` …）。
- 對含敏感欄位的字串（如 `personal_id`、`token`）做 redact。
- 提供 `RuntimeLogManager` 單例 + 公開 API。

## 公開 API
| 函式 | 用途 |
|------|------|
| `configure_runtime_logging(enabled, base_dir="")` | 啟用 / 停用 logging；回傳目前日誌路徑 |
| `read_file_logging_flag(config_path, default=True)` | 從 `config.json` 讀取 `file_logging_enabled` |
| `write_log_event(level, message)` | 由 GUI / 程式手動呼叫寫一行 log |
| `get_runtime_log_path()` | 取得目前的 `program.log.<YYYYMMDD>` 路徑 |
| `is_runtime_logging_enabled()` | 目前 logging 是否啟用 |
| `compose_log_message(level, message, *, include_traceback=None, exc_info=None)` | 自動把 traceback 黏到訊息尾 |
| `normalize_log_lines_for_file(text)` | 把多行訊息精簡為「程式關注的」幾行 |
| `strip_log_control_codes(text)` | 移除 ANSI escape 與不可見字元 |
| `build_runtime_log_path(base_dir="", now=None)` | 算出當日 log 路徑（不會寫檔） |

## 內部結構
- `RuntimeLogManager`：
  - `_TeeStream`：包裝 stdout/stderr，寫原 stream 之餘也轉送到 log。
  - 安裝 `sys.excepthook` 與 `threading.excepthook`，捕捉未處理例外。
  - 用 `threading.Lock` + 行緩衝（`_stream_buffers`），確保多執行緒寫入順序。
  - `_filter_stream_lines` 套用雜訊 / traceback header 過濾。

## 與其他模組關係
- `main.py` 啟動時呼叫 `configure_runtime_logging`。
- `gui.push_log` 也會呼叫 `write_log_event` 把 GUI 訊息同時寫入檔案。
- 不應被 `broker.*` 直接依賴；broker 內部走 Python `logging` 體系。

## Side Effect
- 建立 `log/program.log.<YYYYMMDD>`（追加模式）。
- 換掉 `sys.stdout / sys.stderr`、`sys.excepthook`、`threading.excepthook`，停用時會還原。

## 注意事項
- 加新的雜訊過濾條件 → 編輯 `_SDK_NOISE_TOKENS` / `_SDK_NOISE_MESSAGES`。
- 過濾 base64 行（避免 SDK 偶爾印出來的 token / 大型 payload）有最小長度限制 40 與可印率 90%。
- `compose_log_message` 預設只在 ERROR / WARN / DEBUG 自動帶 traceback；其他層級需明示 `include_traceback=True`。

## 對應測試
- `build_win/src/tests/test_logging.py`
