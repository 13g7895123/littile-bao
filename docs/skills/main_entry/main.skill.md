# Skill：程式進入點 `main.py`

## 檔案位置
- `build_win/src/main.py`

## 主要職責
- 啟動 PyQt6 應用程式並建立 `gui.App` 主視窗。
- 初始化執行時 logging（`app_logging`），決定是否寫實體 log 檔。
- 載入 `BrokerSettings`，選擇要使用 `FubonAdapter` 還是 `MockAdapter` 並進行登入。
- 捕捉啟動階段的未捕捉例外，寫入 `startup_crash.log` 並提示路徑。

## 主要函式
| 名稱 | 功能 |
|------|------|
| `_log_dir()` | 取得 log / config.json 所在目錄；frozen 時取 exe 同層，否則取 src 目錄。 |
| `_init_runtime_logging()` | 依 `config.json` 的 `file_logging_enabled` 決定是否啟用 file logging，並回傳 log 路徑。 |
| `main()` | 程式主流程：載入設定 → 建 broker → 開 GUI → `app.exec()`。 |
| `_init_broker(settings)` | 依 `BrokerSettings.mock_mode` / `is_complete()` 決定使用 Mock 或 Fubon；Fubon 登入失敗會降級為 Mock。 |

## 與其他模組關係
- 讀：`config.BrokerSettings`、`app_logging.*`
- 動態 import：`PyQt6`、`config`、`engine`、`gui`、`broker`
- 呼叫：`gui.App().set_broker(adapter)`

## Side Effect
- `print(...)` 與 logging：開機階段資訊。
- 若例外：寫入 `<exe_dir>/startup_crash.log`。
- 阻塞於 `app.exec()` 直到 GUI 關閉。

## 注意事項
- 須在 `sys.path` 插入 `src/` 目錄後才能 import 各模組（已在頂端做掉）。
- `getattr(sys, 'frozen', False)` 是 PyInstaller 打包時的旗標，用以區分執行檔模式。
- 任何啟動失敗都應該被 `try/except` 在 `__main__` 收住，避免黑視窗直接消失。
