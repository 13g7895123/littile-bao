# Skill：GUI 盤中行情錄製整合

## 涉及方法
- `_maybe_attach_recorder(cfg, feed, symbol_infos)`
- `_stop_recorder()`

## 行為
- 啟動策略時若 `cfg.recording_enabled=True` 且 `feed.attach_recorder` 可用：
  1. 先收掉舊 `self._recorder`（保險）。
  2. 解析 `cfg.recording_dir` → `Path` 或預設 `default_recording_root()`。
  3. `cleanup_old_recordings(root, cfg.recording_keep_days)` 清除過期錄製。
  4. 建立 `RecordingWriter(out_root=root, log_cb=push_log)`。
  5. 組 `meta`：含 `config_snapshot` (`dataclasses.asdict(cfg)`)、`symbol_universe` 與 `symbol_count`。
  6. `writer.start(meta=...)` → `feed.attach_recorder(writer, record_raw=cfg.recording_record_raw)`。
  7. 將 writer 存到 `self._recorder`，並 push_log 顯示 session 路徑。
- 失敗一律降級為「不錄製」並 push_log("WARN", ...)。

## `_stop_recorder()`
- 若 `self._recorder` 存在 → 設為 `None`、在背景 thread 內呼叫 `rec.close()`，避免阻塞 UI。

## 設定欄位對應
| `TradingConfig` | 行為 |
|------|------|
| `recording_enabled` | 是否啟用錄製 |
| `recording_dir` | 自訂輸出根目錄；空字串 → 預設 |
| `recording_keep_days` | 保留天數；<=0 → 不清理 |
| `recording_record_raw` | 是否同時錄 SDK raw JSON |

## 注意事項
- Mock feed 沒有 `attach_recorder` → 跳過 + INFO log 通知使用者。
- close 失敗只 log warning，不影響其他流程。
- 啟動失敗時要在 `_start_trading_worker` 的 except 中明確呼叫 `_stop_recorder()`，避免殘留 thread。
