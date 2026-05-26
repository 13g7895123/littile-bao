# Skill：`TradingConfig`（策略 / 系統設定）

## 檔案位置
- `build_win/src/config.py`

## 主要職責
- 集中保存所有「策略可調參數」與「系統參數」。
- 以 `config.json` 為主要持久化來源（位於 exe 或 src 同目錄）。
- 提供 `load()` / `load_strict()` / `save()` / `from_dict()` 四種讀寫介面。
- 內建欄位升級機制（例如把舊版 `limit_up_detection_mode` 升級為 `strict_lock_from_user_rule`）。

## 主要欄位（依功能編號）

| 區塊 | 欄位 | 預設 | 用途 |
|------|------|------|------|
| 功能 1（10 點前漲停 + 委賣張數） | `f1_enabled`, `start_time`, `entry_before_time`, `ask_queue_threshold` | True / 09:00 / 10:00 / 100 | 進場條件 |
| 功能 2（市場） | `market_twse`, `market_tpex` | True / True | 市場篩選 |
| 功能 3（每檔金額） | `per_stock_amount` | 100,000 | 進場金額 |
| 功能 4（漲停打開賣出） | `f4_enabled`, `f4_open_ticks_to_sell`, `f4_require_today_limitup` | True / 1 / True | 出場條件 |
| 功能 5（1 秒成交量） | `f5_enabled`, `volume_spike_sell_threshold` | True / 499 | 出場 |
| 功能 6（排隊取消） | `f6_enabled`, `volume_spike_cancel_threshold` | True / 499 | 委託取消 |
| 功能 7（K 棒限制） | `f7_enabled`, `candle_limit` | True / 2 | 起漲 K 棒 |
| 功能 8（當日量門檻） | `f8_enabled`, `daily_volume_min` | True / 500 | 進場過濾 |
| 功能 9（價格區間） | `f9_enabled`, `price_min`, `price_max` | True / 10.0 / 500.0 | 進場過濾 |
| 功能 10（價量雙確認） | `f10_enabled`, `ask_price_ratio`, `entry_volume_confirm` | True / 1.0 / 50 | 進場過濾 |
| 功能 11（排除特殊股） | `f11_enabled` | True | 進場過濾 |
| 功能 12（開盤即漲停） | `f12_enabled`, `f_open_limitup_entry_enabled` | True / True | 進場控制 |
| 功能 13（每日最大檔數） | `f13_enabled`, `daily_max_trades` | True / 5 | 風控 |
| 消化量進場 | `f_consume_enabled`, `consume_qty_threshold`, `consume_mutex_with_f1` | False / 499 / True | 進場另一條規則 |
| 下單模式 | `order_dry_run` | True | 模擬下單 |
| 系統 | `file_logging_enabled` | True | 是否寫實體 log |
| 盤中錄製 | `recording_enabled`, `recording_dir`, `recording_keep_days`, `recording_record_raw` | False / "" / 7 / True | Phase1 錄製 |
| 鎖板判斷模式 | `limit_up_detection_mode` | `strict_lock_from_user_rule` | 對應 `limitup_detection` 模式名 |
| 帳號（舊欄位，已轉至 BrokerSettings） | `api_id`, `api_key`, `broker_cert_path` | "" | 相容欄位 |
| 黑名單 | `blacklist` | `[]` | 排除清單 |

## 主要 API
- `TradingConfig.load(path="")`：載入 `config.json`，失敗時回傳預設物件。
- `TradingConfig.load_strict(path)`：失敗會拋例外（GUI 重置時使用）。
- `TradingConfig.from_dict(data)`：自動忽略未知欄位 + 升級舊 `limit_up_detection_mode`。
- `cfg.save(path="")`：JSON 寫回（縮排 2、UTF-8）。
- `cfg.get_markets()`：依 `market_twse / market_tpex` 回傳 `["TSE", "OTC"]` 子集合。

## 與其他模組關係
- 被 `engine.TradingEngine` 直接讀取。
- 被 `gui.App._collect_config / _apply_config` 對應到 UI 欄位。
- 鎖板模式名稱與 `limitup_detection.LIMIT_UP_DETECTION_MODES` 對齊。

## 注意事項
- **新增欄位時務必**：
  1. 加在 `TradingConfig` 對應位置 + 預設值。
  2. 確認 `from_dict()` 不會把它擋掉（會自動以 `__dataclass_fields__` 過濾）。
  3. GUI 需要編輯 → 補 `_apply_config / _collect_config`。
- 設定升級邏輯（例如鎖板模式相容處理）統一寫在 `from_dict()`。

## 對應測試
- `build_win/src/tests/test_config.py`
