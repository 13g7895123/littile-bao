# Skill：Windows 執行環境路徑對照

## 用途
- 查找這個專案在 Windows 執行檔環境中的 `config`、`log`、`recordings`、`dry-run audit` 實際位置。
- 在 WSL / Linux 工作區分析檔案時，快速把 Windows 路徑換成可讀取的 `/mnt/c/...` 路徑。

## 常用對照
| 用途 | Windows 路徑 | WSL 路徑 |
|------|--------------|----------|
| 專案根目錄 | `C:\Jarvis\15_bonus\01_littile-bao` | `/mnt/c/Jarvis/15_bonus/01_littile-bao` |
| 執行檔輸出目錄 | `C:\Jarvis\15_bonus\01_littile-bao\build_win\dist` | `/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist` |
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
- WSL 讀取 `.gz` 錄製檔時，若檔案在收盤前中斷，`gzip` 可能出現 `EOFError`；分析時要容忍截斷尾端。
- 若要比對 GUI 顯示與引擎判斷，優先交叉看：
  - `program.log.YYYYMMDD`
  - `dry_run_audit_YYYYMMDD.jsonl`
  - `log/recordings/YYYYMMDD/session_*.ticks.ndjson.gz`
