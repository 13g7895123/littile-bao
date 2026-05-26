# Skill：GUI 券商設定頁

## 涉及方法
- `_build_broker_page(parent)`
- `_browse_cert()`
- `_broker_apply_settings(settings)`
- `_broker_load_default_json() / _broker_import_json() / _broker_export_json()`
- `_broker_fields_to_settings()`
- `_broker_test_connection() / _broker_connect()`
- `_set_broker_page_status / _refresh_broker_status / _set_broker_status`

## 欄位（`self._bfields`）
- `personal_id, password, cert_path, cert_password, branch_no, account_no, api_key, api_secret`
- 開關：`self._toggles["broker_dry_run"]`、Mock 模式按鈕

## 主要動作
| 操作 | 對應方法 |
|------|----------|
| 「瀏覽憑證」按鈕 | `_browse_cert` 開 QFileDialog 並把路徑寫入 `cert_path` |
| 載入預設 JSON | `_broker_load_default_json` 從 `BROKER_SETTINGS_FILE` 載入 |
| 匯入 JSON | `_broker_import_json` 開檔對話框 + `BrokerSettings.load_strict` |
| 匯出 JSON | `_broker_export_json` 開存檔對話框 + `settings.save(path)` |
| 測試連線 | `_broker_test_connection`：以 `FubonAdapter.from_config(settings).login()` 試一次 |
| 套用並登入 | `_broker_connect`：等同 `main._init_broker(...)` 流程，成功後 `set_broker` |

## 狀態顯示
- `_broker_conn_lbl`：顯示「待連線 / 連線中 / 連線成功：分行-帳號 / 錯誤：...」。
- `_set_broker_page_status(text, color)`：寫頁內小狀態。
- `_set_broker_status(text, dot_color, text_color)`：寫狀態列。

## 注意事項
- 任何更新欄位都必須走 `BrokerSettings`（避免散落的 dict）。
- 加新欄位時要同時：
  - 在 `BrokerSettings` 加欄位（含預設值）。
  - 在 `_broker_apply_settings / _broker_fields_to_settings` 雙向綁定。
  - 視需要加 UI 控件 + 提示。
- 預設 JSON 路徑由 `config.BROKER_SETTINGS_FILE` 提供，請勿在 GUI 寫死。
