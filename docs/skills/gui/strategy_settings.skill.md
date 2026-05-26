# Skill：GUI 策略設定（側欄 + 全頁）

## 涉及方法
- `_create_strategy_settings_panel()` — 建立設定面板（共用於儀表板側欄與設定頁）
- `_set_strategy_panel_mode(*, full_page)` / `_place_strategy_settings_panel(*, full_page)`
- `_populate_limit_up_mode_combo(combo)` / `_set_limit_up_mode_selection(mode)` / `_get_selected_limit_up_mode` / `_apply_limit_up_mode(mode, log_change=True)`
- `_sf(form, lbl, key, ...)` — 加單一表單欄位的 helper
- `_apply_config(cfg) / _collect_config()`
- `_save_settings / _export_settings_json / _import_settings_json / _reset_settings`
- `_on_strategy_toggle(enabled)`
- `_on_order_mode_toggled(dry_run)` / `_on_mock_mode_toggled(use_mock)`
- `_switch_to_mock_broker() / _switch_to_fubon_broker() / _update_mock_mode_label`

## 設定面板內容
- 對應 `TradingConfig` 所有欄位的 `QLineEdit / QCheckBox / QComboBox / ToggleButton`。
- 鎖板判斷模式下拉：選項從 `LIMIT_UP_DETECTION_MODES` 動態填入。
- 模擬 / 真實下單切換、Mock / Fubon broker 切換。

## `_apply_config / _collect_config`
- `_apply_config(cfg)`：把 `TradingConfig` 套用到所有控件值。
- `_collect_config()`：從所有控件回收成新的 `TradingConfig`；不會 save。

## `_save_settings`
- 由「儲存設定」按鈕觸發：先 `_collect_config()`，再 `cfg.save()`，最後若引擎已啟動則熱套用：
  - 嘗試呼叫 `engine.replace_universe(...)` + `resubscribe_feed()` 切換訂閱清單。
  - `engine.update_limit_up_mode(mode)` 立即套用新模式。

## `_on_order_mode_toggled / _on_mock_mode_toggled`
- 下單模式切換時若已連線 Fubon → 呼叫 `broker.set_dry_run(...)` 重建 OrderManager。
- Mock 切換：清掉現有 broker、改用 `MockAdapter`，並重置 GUI 狀態。

## 注意事項
- 新增策略欄位時：
  1. 在 `TradingConfig` 加欄位。
  2. 在 `_create_strategy_settings_panel` 加對應控件（`_sf` helper）。
  3. 在 `_apply_config` / `_collect_config` 加映射。
  4. 視需求加進「事件日誌 / 監控」顯示。
- 控件名稱請統一存進 `self._fields / _checks / _toggles / _combos`，方便迭代。
- 修改鎖板模式下拉選項：直接更新 `LIMIT_UP_DETECTION_MODES`，無需改 GUI。
