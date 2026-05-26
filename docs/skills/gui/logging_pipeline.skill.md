# Skill：GUI 日誌訊息流程

## 涉及方法 / 變數
- 模組層級：`push_log(level, msg, *, include_traceback=None)`、`LOG_Q`、`LIMIT_UP_SIGNAL_LABELS`
- App：`_start_polling / _drain_log_queue`（透過 QTimer 排程）
- App：`_append_log_html_to_views / _render_log_views / _is_strategy_log / _log_entry_visible`
- App：`_add_log_filter_buttons / _set_log_filter / _sync_log_filter_buttons`
- App：`_clear_log`

## 整體流程
```
engine / broker / gui code
        │ on_log(level, msg)  /  直接 push_log(...)
        ▼
push_log()
   ├─ write_log_event(level, compose_log_message(...))   # 寫入 program.log.YYYYMMDD
   └─ LOG_Q.put((level, msg))                            # 投入 UI queue
        ▼
QTimer (每 100~200ms) 在主執行緒 drain LOG_Q
   ├─ _log_entries.append({...})
   └─ _append_log_html_to_views(html_text)               # 寫到 event_log + events_full_log
```

## 篩選機制
- `_log_filter`：`"all"` 或 `"strategy"`。
- `_is_strategy_log(level, msg)` 判斷某筆 log 是否屬於策略類（依 level / 內容字串）。
- `_log_entry_visible(entry)` 根據 filter 決定是否顯示在事件日誌。
- 切換 filter 後 `_render_log_views()` 重畫所有歷史 log。

## 顏色與字級
- `self._log_colors = {"INFO", "TRADE", "WARN", "ERROR", "DEBUG"}` → 對應 `C` 內顏色。
- 訊息以 HTML 寫入 `QTextEdit`，level 與時間用 `<span color=...>` 包起來。

## 注意事項
- 任何訊息一律走 `push_log`，禁止直接呼叫 `self.event_log.append(...)`，否則：
  - 不會進 `LOG_Q` → 不會寫進實體 log。
  - 不會經 filter / coloring → 樣式不一致。
- `LOG_Q` 為 thread-safe `queue.Queue`；多 thread 寫入安全。
- 新增 log level → 更新 `_log_colors`、`_is_strategy_log`、`compose_log_message` 行為（如需 traceback）。
