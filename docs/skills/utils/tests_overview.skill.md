# Skill：測試套件總覽

## 目錄
- `build_win/src/tests/`

## 測試檔對應
| 測試檔 | 對應 skill |
|--------|------------|
| `test_config.py` | [`config/trading_config.skill.md`](../config/trading_config.skill.md) |
| `test_account.py` | [`broker/account/account_service.skill.md`](../broker/account/account_service.skill.md) |
| `test_broker.py` | [`broker/adapter/*`](../broker/adapter/) |
| `test_orders.py` | [`broker/orders/*`](../broker/orders/) |
| `test_realtime.py` | [`broker/realtime/*`](../broker/realtime/) |
| `test_universe.py` | [`broker/universe/*`](../broker/universe/) |
| `test_fees.py` | [`broker/models_errors_fees.skill.md`](../broker/models_errors_fees.skill.md) |
| `test_logging.py` | [`app_logging/app_logging.skill.md`](../app_logging/app_logging.skill.md) |
| `test_engine_strategy.py` | [`engine/strategy_loop.skill.md`](../engine/strategy_loop.skill.md) |
| `test_gui_tabs.py` | [`gui/`](../gui/) 系列分頁 |

## 執行
```bash
cd build_win/src
python -m pytest tests/
```
或：
```bash
python -m unittest discover -v build_win/src/tests
```

## 注意事項
- `test_gui_tabs.py` 會啟動 `QApplication`，部分環境（無 X server）需設 `QT_QPA_PLATFORM=offscreen`。
- 引擎相關測試 (`test_engine_strategy.py`) 使用 `MockAdapter` + 模擬 tick / book，**不依賴真實 SDK**。
- 新增 / 修改邏輯時請同步補測試；測試命名請對應功能編號（例如 F4 出場 → `test_f4_*`），便於 trace。
