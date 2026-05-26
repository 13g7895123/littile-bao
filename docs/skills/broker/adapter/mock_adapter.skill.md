# Skill：`MockAdapter`

## 檔案位置
- `build_win/src/broker/adapter.py`

## 主要職責
- 無券商憑證 / Demo / 測試用的假適配器。
- 立刻「登入成功」並回一個固定 mock 帳號 `0000-0000000 / 模擬帳號`。
- 行情 / 個股資料 / 下單一律走對應的 Mock 實作。

## 主要方法
| 方法 | 行為 |
|------|------|
| `login()` | 切到 `CONNECTED`，建立 mock `AccountRef`，回 `LoginResult(success=True)` |
| `logout()` | 切回 `DISCONNECTED`，清空已選帳號 |
| `create_realtime_feed()` | 回傳 `MockRealtimeFeed` |
| `load_symbol_info(codes)` | 用 `DEFAULT_MOCK_INFOS` 包成 `StaticSymbolInfoLoader` 回傳 |
| `_get_order_manager()` | 第一次呼叫時建立 `MockOrderManager(self)`；之後重用 |
| `account_service()` | Lazy 建立 `MockAccountService`，並訂閱 `on_filled` 自動更新部位 |
| `_sync_mock_account(ev)` | 收到成交時動態更新 `_mock_positions`，並寫回 `MockAccountService` |

## 帳戶模擬規則
- 買進：若該檔不存在 → 建立 `Position`；存在 → 加總張數並重算平均成本。
- 賣出：直接從 `_mock_positions` 移除（簡化）。
- 模擬市值 = `price * qty * 1000`（張×1000 股）。

## 注意事項
- 修改 mock 行為時要保留：「登入即成功」「永遠有一個帳號」。
- 若新增 `BrokerAdapter` 抽象方法，這裡也要補 mock 實作（即便回空集合）。
- 不應在 mock 內呼叫真實網路 / SDK。
