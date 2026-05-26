# Skill：`FubonAdapter`

## 檔案位置
- `build_win/src/broker/adapter.py`

## 主要職責
- 包裝 `fubon_neo` SDK 的 thread-safe 單例適配器。
- 支援三種登入模式：`apikey_dma` / `apikey` / `password`（依 `BrokerSettings.login_mode`）。
- 提供 SDK 物件 (`self.sdk`)、登入後帳號清單、帳號切換。
- 將 SDK 推送的成交 callback 轉成內部 `FillEvent` 再廣播。
- 依 `dry_run` 旗標自動切換成 `DryRunOrderManager` 或 `FubonOrderManager`。
- `account_service()` 回 `FubonAccountService`，可呼叫 SDK 庫存 / 帳務 API。

## 工廠 / 單例
- `FubonAdapter.from_config(cfg: BrokerSettings)`：建構新實例。
- `FubonAdapter.instance(cfg=None)`：第一次需提供 cfg，之後皆回同一實例。

## 主要方法
| 方法 | 行為 |
|------|------|
| `login()` | 動態 import `FubonSDK`，依模式呼叫 `apikey_dma_login / apikey_login / login`；成功時掛 SDK 成交 callback |
| `logout()` | 嘗試呼叫 SDK 的 `logout()`，清掉 `_sdk` |
| `select_account(branch_no, account_no)` | 從 `_accounts` 找對應，找不到回第一個（並記錄） |
| `create_realtime_feed()` | 回 `FubonRealtimeFeed(self)` |
| `load_symbol_info(codes)` | 走 `FubonSymbolInfoLoader(self).load(codes)` |
| `_get_order_manager()` | `dry_run=True` → `DryRunOrderManager`；否則 `FubonOrderManager` |
| `set_dry_run(enabled)` | 切換並丟棄已建立的 OrderManager（下次重建） |
| `_attach_sdk_fill_handler()` | 把 SDK 的 `set_on_filled` 串到 `dispatch_fill` |
| `_convert_sdk_fill(content)` | 將 SDK 成交內容轉為 `FillEvent`；解析 `stock_no / buy_sell / filled_price / filled_qty` 等 |

## 例外行為
- `from fubon_neo.sdk import FubonSDK` 失敗 → `FubonAuthError("未安裝 fubon_neo SDK ...")`。
- 登入 SDK 回 `is_success=False` → `FubonAuthError("Fubon login 失敗：<msg>")`。
- 其他未預期錯 → `FubonAuthError("登入時發生未預期錯誤：...")`。
- 未登入呼叫 `self.sdk` → `FubonNotLoggedInError`。

## 與其他模組關係
- `main._init_broker` 失敗時降級為 `MockAdapter`。
- 與 `broker.realtime.FubonRealtimeFeed` 共用 `self.sdk`。
- 與 `broker.orders.FubonOrderManager / DryRunOrderManager` 共用 `self.sdk + self.account`。

## 注意事項
- `cert_password` 預設值為 `personal_id`（SDK 1.3.2+ 行為）。
- 任何新增的下單 / 行情 / 帳務功能：請優先在 broker 層加方法，避免 gui / engine 直接呼叫 SDK。
- 動態 import SDK：保留延遲載入，避免無 SDK 環境（如測試）報 ImportError。
