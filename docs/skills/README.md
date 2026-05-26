# Skills 索引

> 本資料夾為「打板策略系統」程式中所有主要物件 / 模組的 skill 描述。
> 每個物件對應一個資料夾，內含 `*.skill.md` 檔。功能較多者再以模組資料夾切分。

## 開發守則（**最重要**）
- [`development_guidelines.skill.md`](./development_guidelines.skill.md) — 開發、維護、修改任何模組前必讀，與如何同步維護 skills。

## 一覽

| 區塊 | 對應原始碼 | skill 位置 |
|------|------------|------------|
| 程式進入點 / Bootstrap | `build_win/src/main.py` | [`main_entry/`](./main_entry/) |
| 設定（策略 / 券商） | `build_win/src/config.py` | [`config/`](./config/) |
| 鎖漲停判斷工具 | `build_win/src/limitup_detection.py` | [`limitup/`](./limitup/) |
| 執行時 Logging | `build_win/src/app_logging.py` | [`app_logging/`](./app_logging/) |
| 策略引擎 | `build_win/src/engine.py` | [`engine/`](./engine/) |
| GUI 介面 | `build_win/src/gui.py` | [`gui/`](./gui/) |
| 券商適配層（含 Mock / Fubon） | `build_win/src/broker/*` | [`broker/`](./broker/) |
| 工具腳本（verify / 分析） | `build_win/src/verify_*.py`、`analyze_limitup_logs.py` | [`utils/`](./utils/) |

## broker 子模組
| 子模組 | skill |
|--------|-------|
| Adapter（連線 / Mock / Fubon） | [`broker/adapter/`](./broker/adapter/) |
| Realtime Feed（行情訂閱） | [`broker/realtime/`](./broker/realtime/) |
| Orders（下單 / Dry-Run） | [`broker/orders/`](./broker/orders/) |
| Account（帳務 / 庫存） | [`broker/account/`](./broker/account/) |
| Universe（選股 / 個股基本資料） | [`broker/universe/`](./broker/universe/) |
| Recording（盤中錄製） | [`broker/recording/`](./broker/recording/) |
| Models / Errors / Fees | [`broker/models_errors_fees.skill.md`](./broker/models_errors_fees.skill.md) |

## 使用流程
1. 開發 / 修改前 → 讀完 [`development_guidelines.skill.md`](./development_guidelines.skill.md)。
2. 找到目標模組對應 skill → 確認職責、輸入/輸出、與其他模組互動。
3. 若需要擴充：**先**更新 skill → 再改程式碼 → **再**回頭校對 skill。
