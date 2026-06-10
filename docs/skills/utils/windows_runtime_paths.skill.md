# Skill：Windows 執行環境路徑對照

## 用途
- 查找這個專案在 Windows 執行檔環境中的 `config`、`log`、`recordings`、`dry-run audit` 實際位置。
- 在 WSL / Linux 工作區分析檔案時，快速把 Windows 路徑換成可讀取的 `/mnt/c/...` 路徑。
- 只要任務是「找交易紀錄 / 委託紀錄 / 成交紀錄 / 當日執行紀錄」，預設先查 Windows `build_win/dist`；repo 內的 `build_win/src/log` 與工作區 `log/` 只當 fallback 或歷史樣本。
- 對這個專案，log 預設根目錄就是 `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log`，不要先從 repo 內 `build_win/src/log` 推斷。

## 預設查找順序
1. 先查 `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist`（WSL: `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist`）。
2. 先鎖定 `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log`，不要改查其他同名 `log/` 目錄。
3. 若使用者提到「交易紀錄」：
   - 先找 `dry_run_audit_YYYYMMDD.jsonl`
   - 再交叉看 `log/program.log.YYYYMMDD`
   - 必要時補 `log/client.log.YYYYMMDD`、`log/notify.log.YYYYMMDD`
4. 若 `dist` 沒有檔案，再退回 repo 內 `build_win/src/log/` 或工作區 `log/`。
5. 回覆使用者時，明確標示資料來自 Windows 路徑還是 fallback 路徑。

## 常用對照
| 用途 | Windows 路徑 | WSL 路徑 |
|------|--------------|----------|
| 專案根目錄 | `C:\Jarvis\15_bonus\01_littile-bao` | `/mnt/c/Jarvis/15_bonus/01_littile-bao` |
| 執行檔輸出目錄 | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist` |
| log 根目錄 | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log` |
| 當日設定檔 | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\config.json` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/config.json` |
| 程式 log | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log\program.log.YYYYMMDD` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/program.log.YYYYMMDD` |
| SDK client log | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log\client.log.YYYYMMDD` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/client.log.YYYYMMDD` |
| SDK notify log | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log\notify.log.YYYYMMDD` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/notify.log.YYYYMMDD` |
| Dry-run 審計檔 | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\dry_run_audit_YYYYMMDD.jsonl` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/dry_run_audit_YYYYMMDD.jsonl` |
| 錄製檔目錄 | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log\recordings\YYYYMMDD` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/recordings/YYYYMMDD` |

## 本專案今天（2026-06-01）常用檔案
- `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\config.json`
- `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\dry_run_audit_20260601.jsonl`
- `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log\program.log.20260601`
- `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log\client.log.20260601`
- `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log\notify.log.20260601`
- `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log\recordings\20260601\session_100909.ticks.ndjson.gz`

## 使用提醒
- Windows log 內可能寫成 `C:/...` 或 `c:\...`，搜尋時兩種都要接受。
- 若目前 agent 的工作目錄是 Linux repo 路徑，例如 `/home/jarvis/project/bonus/03_littile-bao`，不要把它誤認成當天 runtime log 所在位置；當天盤中資料仍優先看 `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist\log`。
- WSL 讀取 `.gz` 錄製檔時，若檔案在收盤前中斷，`gzip` 可能出現 `EOFError`；分析時要容忍截斷尾端。
- 若要比對 GUI 顯示與引擎判斷，優先交叉看：
  - `program.log.YYYYMMDD`
  - `dry_run_audit_YYYYMMDD.jsonl`
  - `log/recordings/YYYYMMDD/session_*.ticks.ndjson.gz`
- 若使用者只說「今天的交易紀錄」，不要先假設 repo 內 `log/` 是最新資料；先去 Windows `build_win/dist` 找當天檔案，再回頭檢查工作區是否只是舊備份。
