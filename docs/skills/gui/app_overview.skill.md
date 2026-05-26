# Skill：GUI 概觀 — `App` 主視窗、配色、UI 元件工廠

## 檔案位置
- `build_win/src/gui.py`

## 主要物件

### `App(QMainWindow)`
- 進入點：由 `main.py` 建立並 `set_broker(adapter)`。
- 屬性：
  - `cfg: TradingConfig`（啟動時 load）
  - `engine: Optional[TradingEngine]`
  - `broker`（由 main 注入）
  - `_recorder`、`_running`、`_strategy_starting / _strategy_start_token`
  - 交易計數：`_trade_count / _buy_count / _sell_count / _daily_trade_codes / _realized_pnl`
  - Log：`_log_lines / _log_entries / _log_filter`
  - UI 控件字典：`_fields / _bfields / _checks / _toggles / _combos / _monitor_rows`
  - 「最新監控快照」：`_latest_monitor_summary`
  - 「儀表板預覽」：`_dashboard_preview_summary / _dashboard_preview_loading / _dashboard_preview_broker_key`
- 跨執行緒 UI 派發：`_ui_dispatch = pyqtSignal(object)`，連到 `_run_ui_dispatch`，外部用 `_dispatch_ui(callback)`。

### `ToggleButton(QWidget)`
- 自繪的開關按鈕（On/Off + 顏色）；`value()` / `set(val)`。

### `push_log(level, msg, *, include_traceback=None)`（模組層級函式）
- 透過 `compose_log_message` + `write_log_event` 寫入 `app_logging` 體系，並把訊息 `put` 到 `LOG_Q` queue。
- GUI 透過 polling LOG_Q 把訊息塞入畫面。

## UI 元件工廠
| 函式 | 用途 |
|------|------|
| `_font(size, bold)` | 統一中文字型 + 字級 |
| `_label(text, color, size, bold)` | 一致風格的 `QLabel` |
| `_entry(width, password)` | `QLineEdit`，可選 password |
| `_combo(items, width)` | 一致樣式的 `QComboBox` |
| `_checkbox(text, size)` | 帶配色的 `QCheckBox` |
| `_divider() / _section_title / _sep_bar` | 分隔與小標題 |
| `_scroll_style() / _table_style()` | QScrollArea / QTableWidget 暗色樣式 |
| `_panel_frame()` | 帶 border 的 `QFrame` 包裝 |

## 配色字典 `C`
- 集中所有色票（背景、面板、邊框、紅綠黃、badge 背景）。**禁止散落 hex code**，新增顏色請加入 `C`。
- `FONT_MAIN = "微軟正黑體"`、`FONT_MONO = "Consolas"`。

## 跨檔資料流
- `engine.on_log` → `self._on_log_event` → `push_log`：寫入 LOG_Q + 顯示。
- `engine.on_trade / on_status / on_strategy_event / on_decision_event` → `_dispatch_ui(...)` → 對應分頁更新。
- `broker.account_service().start_polling(self._on_account_snapshot, interval=10)`：每 10 秒更新「庫存 / 損益 / 買進力」。

## 注意事項
- 任何 UI 變更必須 marshal 回 Qt 主執行緒（用 `_dispatch_ui`），勿從 callback thread 直接 `setText / addItem`。
- 新增分頁：
  1. 在 `_build_body` 的 `_pages` dict 加 key。
  2. 在 `_build_<key>_page(parent)` 內建立內容。
  3. 在 `_tab_btns` / `_switch_tab` 補對應 case。
- 任何「全 app 字串 / 色彩」變更皆應改 `C` / `LIMIT_UP_SIGNAL_LABELS` 等模組常數。
