# Skill：每日盤後交易整理

## 檔案位置
- `build_win/src/generate_daily_trade_report.py`

## 用途
- 根據 `dry_run_audit_YYYYMMDD.jsonl`、`program.log.YYYYMMDD`、`client.log.YYYYMMDD`，生成每日盤後交易整理初稿。
- 用於：
  - 固定輸出每日成交摘要、損益、買賣明細、未平倉部位。
  - 補抓盤中重登入、重連、日內計數重置、鎖漲停模式切換等關鍵事件。
  - 排除時鐘偏移 / 延遲失真區段的成交，只保留可採信時間基準之後的成交。
  - 輸出客戶版報告，只呈現正式採用的成交與結論，不呈現錯誤、偏移、修復、排除細節。

## 使用方式
```bash
python3 build_win/src/generate_daily_trade_report.py \
  --date 2026-06-04 \
  --audit /mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/dry_run_audit_20260604.jsonl \
  --program-log /mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/program.log.20260604 \
  --client-log /mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/client.log.20260604 \
  --config /mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/src/config.json \
  --output docs/2026-06-04_交易整理.zh-tw.md
```

## 產出內容
- `資料來源`：列出 audit / log / config 路徑。
- `重要前提`：固定說明 dry-run、費率規則、報告依據。
- `重要前提` 只需明寫本日正式採用的成交區段起點，不要解釋偏移、錯誤、修復過程。
- `今日總覽`：買賣成交筆數、未平倉檔數 / 張數、買賣金額、已實現損益、未平倉成本。
- `策略與參數摘要`：從 `program.log` 推估當日實際執行的進場截止、F4 / F5 門檻、鎖漲停判斷模式。
- `執行階段事件`：登入、連線完成、重登入、`今日第 1 檔` 重置、啟用時已鎖漲停股票。
- `賣出觸發分布`、`已實現虧損排序`、`買進成交清單`、`賣出成交清單`、`未平倉部位`、`觀察與結論`。

## 核心邏輯
- 先根據 `program.log` 的 `[時鐘偏移]` 與 `latency_summary` 找出本日第一段可採信時間基準。
  - 若存在重啟後才恢復正常的區段，以恢復正常後的啟動時間作為報告 cutoff。
  - 若使用者明確指定 cutoff，例如「只保留 2026-06-26 09:23:00 之後」，必須直接採用。
- 只讀取 audit 內的 `FILL` 事件，忽略 `PLACE`。
- 只統計 `ts >= cutoff` 的 `FILL`。
- 任何 `ts < cutoff` 的偏移區成交，都不得出現在：
  - `今日總覽`
  - `賣出觸發分布`
  - `已實現虧損排序`
  - `買進成交清單`
  - `賣出成交清單`
  - `未平倉部位`
- 依股票代號做 FIFO 配對，計算已實現損益與剩餘未平倉部位。
- 手續費 / 交易稅規則與 `broker.fees` 一致：
  - 手續費：`0.1425% × 0.6`，最低 `20` 元，無條件捨去到整數。
  - 交易稅：當沖 `0.15%`，無條件捨去到整數。
- `program.log` 額外抽取：
  - `鎖漲停判斷模式：...`
  - `今日第 1 檔`
  - `啟用時已鎖漲停`
  - `F1:已過進場時段`
  - `達出場門檻 N 檔`
  - `1秒量 X 張 > Y 張`
- `client.log` 額外抽取：
  - `apikey_login`
  - `logout`

## 使用注意
- 若 `config.json` 與實際執行不一致，以 `program.log` 觀察值為準。這在 GUI 手動改參數、盤中重連後尤其常見。
- 客戶版報告不可寫入：
  - 時鐘偏移數字
  - 延遲惡化 / 修復細節
  - 錯誤訊息
  - 「程式啟用後已漲停」這類內部診斷描述
- 偏移區成交不能混入正式成交統計；對客戶只保留正式採用結果，不需交代排除過程。
- 腳本會自動產出結論段，但仍應人工複核：
  - cutoff 是否抓對，是否真的從可採信區段開始計算。
  - 是否有盤中重啟或重登入造成日內計數重置。
  - 鎖漲停判斷模式是否盤中切換。
  - `open_ticks` 數字是否需要再用 recording 驗證。
- 若某日有部分成交、分批賣出或跨多次同代號買進，FIFO 配對會影響單筆已實現損益歸屬；這與目前報表的逐筆成交邏輯相符。
