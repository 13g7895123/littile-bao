# Skill：GUI 策略啟動 / 停止流程

## 涉及方法
- `_on_strategy_toggle(enabled)` — 主開關 (`ToggleButton`) 的回呼
- `_start_trading()` — 啟動準備：擋收盤、reset 計數、開背景 worker
- `_start_trading_worker(token, cfg, broker)` — 背景執行緒
- `_is_start_token_current(token)` — 防止重複啟動 / 中途取消的 token 機制
- `_load_trading_runtime(broker, cfg)` — 載入 symbol_infos + 建 feed（封裝 broker / scan / cache 流程）
- `_confirm_fubon_special_candidates(loader, candidates, cfg)` / `_special_flag_reasons(info)`
- `_finish_start_trading(token, engine)` — 成功收尾
- `_fail_start_trading(token, error)` — 失敗收尾
- `_stop_trading()` — 停止流程
- `_rescan_universe_with_progress()` — 設定變動後重掃宇宙
- `_sell_all_strategy_positions()` — 「手動全賣」按鈕

## 啟動流程
1. **前置檢查**：
   - 至少選一個市場。
   - 若收盤後 (`_is_after_market_close()`) → 不啟動策略，改執行收盤預覽。
2. **狀態初始化**：清空 PnL / 計數、清空決策明細、切換徽章為「載入中」。
3. **背景 worker**：`_start_trading_worker` 在 daemon thread 跑：
   1. `_load_trading_runtime(broker, cfg)` 取得 `symbol_infos` 與 `feed`。
   2. （可選）`_maybe_attach_recorder(cfg, feed, symbol_infos)` 掛上行情錄製。
   3. 建立 `TradingEngine(..., on_log=push_log, on_trade=self._on_trade, on_status=lambda s: None, on_strategy_event=self._on_strategy_event, on_decision_event=self._on_decision_event, feed=feed, symbol_infos=symbol_infos, broker=broker)`。
   4. `engine.start()`。
   5. 若 token 已被新一輪取代 → `engine.stop()` + `_stop_recorder()` 後 return。
   6. `_dispatch_ui(self._finish_start_trading(token, engine))`。
4. **異常處理**：捕到 Exception → `_stop_recorder()` + 切 UI 顯示「啟動失敗」。

## Token 機制
- `self._strategy_start_token`：每次啟動 +1；worker 中比對 token 是否仍最新，避免「使用者快速 toggle 開關」造成多 engine 並存。

## 停止流程 `_stop_trading()`
- 切換徽章 → `stop` engine → `_stop_recorder()` → 重新啟用設定編輯。

## 重新掃描 `_rescan_universe_with_progress`
- 由「重新掃描」按鈕觸發；走背景流程載入新 `symbol_infos`，再呼叫 `engine.replace_universe + resubscribe_feed`。

## 手動賣出 `_sell_all_strategy_positions`
- 呼叫 `engine.sell_all_strategy_positions(reason)`；只賣出引擎追蹤的部位（不會動到自行下單的庫存）。

## 注意事項
- 任何修改流程都要保留：
  - 收盤分支（避免盤後誤訂閱）。
  - Token 機制（避免重複啟動 / race condition）。
  - `_stop_recorder()` 與 `engine.stop()` 在 finally 路徑都會跑到，避免 thread / 檔案殘留。
- `_load_trading_runtime` 中所有 broker / cache / scan 來源請優先重用 `broker.universe.*`，不要在 gui 內自行重寫掃描邏輯。
