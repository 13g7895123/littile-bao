# Skill：`BrokerSettings`（券商連線設定）

## 檔案位置
- `build_win/src/config.py`

## 主要職責
- 儲存 / 載入富邦 Neo SDK 登入所需的個資、API Key、憑證資訊與 Dry-Run 設定。
- 主檔案：`broker_settings.json`，位於 exe 或 src 同目錄。
- 維持與舊版 `.env` 的相容：`from_env()` 仍可用。
- 自動判定登入模式：`apikey_dma` / `apikey` / `password`。

## 主要欄位
| 欄位 | 說明 |
|------|------|
| `personal_id` | 身分證字號 / 客戶代號 |
| `password` | 網路下單密碼（密碼模式必填） |
| `cert_path` | 憑證檔案路徑（apikey 或 password 模式） |
| `cert_password` | 憑證密碼；空字串時 SDK 預設等同 `personal_id` |
| `branch_no` / `account_no` | 分行 / 帳號（密碼模式） |
| `api_key` / `api_secret` | API Key 模式憑據 |
| `dry_run` | True 時下單會走 `DryRunOrderManager`，不送真實單 |
| `dry_run_use_market_price` | Dry-Run 模擬成交時是否使用即時報價 |
| `dry_run_fill_min_sec` / `dry_run_fill_max_sec` | Dry-Run 成交模擬延遲（秒） |
| `dry_run_audit_dir` | Dry-Run 審計檔輸出目錄；空字串使用預設位置 |
| `mock_mode` | True → 強制使用 `MockAdapter` |

## 主要 API
- `BrokerSettings.load(path="")` / `load_strict(path)` / `from_dict(data)` / `from_env()`
- `cfg.save(path="")`
- `cfg.login_mode` (`apikey` / `apikey_dma` / `password`)
- `cfg.is_complete()` → 是否備齊該登入模式所需欄位
- `cfg.missing_fields()` → 列出缺失欄位中文名（給 UI 顯示）

## 與其他模組關係
- 被 `main._init_broker()` 與 `gui` 券商頁籤直接讀寫。
- 被 `broker.adapter.FubonAdapter.from_config()` 轉換成 SDK 連線參數。

## 注意事項
- `cert_password` 預設值 = `personal_id`（SDK 1.3.2+ 行為），切勿在 UI 強制要求。
- `from_env()` 使用 `_load_dotenv()` 嘗試讀 `.env`；若沒有 python-dotenv 會用手動解析的 fallback。
- 新增欄位時若希望 GUI 也能編輯，需同步更新 `_build_broker_page` 對應控制項。
