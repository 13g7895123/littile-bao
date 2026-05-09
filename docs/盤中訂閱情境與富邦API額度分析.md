# 盤中訂閱情境與富邦 API 額度分析

日期：2026-05-09

## 結論摘要

以目前專案設計，盤中策略啟動時會先用 REST 快照取得市場資料，篩選出最多 500 檔候選股，然後對候選股訂閱即時行情 `trades` 與 `books`。

若保守把一個 `(channel, symbol)` 視為一筆 WebSocket 訂閱，則：

```text
訂閱數 = 候選股檔數 × channel 數
       = 候選股檔數 × 2
```

富邦行情額度目前可用的判斷基準：

| 類型 | 官方限制 | 本專案影響 |
|---|---:|---|
| WebSocket | 單一連線 200 訂閱；同帳號最多 5 連線 | 理論總量 1000 訂閱 |
| 行情快照 | 300/min | 全市場 snapshot 正常只需上市/上櫃各一次，安全 |
| 日內行情 REST | 300/min | 只有 fallback 逐支查詢時風險較高 |
| 歷史行情 REST | 60/min | 補查候選股日 K 時需控速 |

目前已實作五連線分片。預設同時訂 `trades + books`，因此每檔股票占 2 筆 WebSocket 訂閱；依富邦 5 條連線、每條 200 訂閱估算，盤中最多可一次監控 500 檔股票。

## 是否已實作五連線訂閱

已確認：已實作。

目前 `build_win/src/broker/realtime.py` 的 `FubonRealtimeFeed` 狀態如下：

| 檢查項目 | 結果 | 說明 |
|---|---|---|
| WebSocket 物件數量 | `self._ws_clients` 最多 5 條 | 第一條優先沿用 SDK 原本 client，額外連線透過 `build_websocket_client()` 建立 |
| 建立連線次數 | 依候選股數建立 1 至 5 條 | 101 檔以上會使用第 2 條；500 檔會開滿 5 條 |
| 股票數上限 | `FUBON_REALTIME_SYMBOL_LIMIT = 500` | 預設 `trades + books`，每檔 2 訂閱，總量 `200 * 5 / 2 = 500` |
| 單連線分片 | 每條最多 100 檔股票 | `100 檔 * 2 channel = 200 訂閱`，不超過富邦單連線額度 |
| 訂閱送出方式 | 每條連線各自送 `trades` 與 `books` | `_do_subscribe()` 依分片後的股票清單逐條送出 |
| 測試覆蓋 | 已補 101 檔與 500 檔分片測試 | 驗證 101 檔使用 2 條、500 檔使用 5 條，且每條不超過 200 訂閱 |

五連線計算基準如下：

```text
單連線訂閱上限 = 200
最大連線數     = 5
總訂閱上限     = 1000
預設 channel   = trades + books = 2
最多股票數     = floor(1000 / 2) = 500
```

## 盤中情境與所需服務

| 情境 | 需要的富邦服務 | 會不會超額 | 備註 |
|---|---|---|---|
| 登入後、策略未啟動，只看儀表板 | 帳戶/庫存 poll：`inventories`、`bank_remain`；候選預覽可能用 `snapshot.quotes` | 通常不會 | 帳戶目前約 10 秒 poll 一次，不屬於行情 WebSocket 訂閱 |
| 盤中啟動策略前載入市場 | REST `snapshot.quotes(market=...)` | 通常不會 | 上市、上櫃各一次即可取得大量資料，遠低於 300/min |
| snapshot 正常，篩選候選股 | 本地 `scan_daily()` | 不會 | 使用已拿到的 snapshot 資料，不額外訂閱 |
| snapshot 失敗，退回逐支 ticker | REST 日內行情 / ticker | 有風險 | 若逐支查 1900+ 檔，會超過 300/min，需要控速或避免走此路徑 |
| 策略監控候選股 | WebSocket `trades` + `books` | 500 檔以內不會 | 500 檔約 1000 訂閱，剛好用滿 5 條連線額度 |
| F1：10 點前 + 漲停委賣低於 N 張進場 | `books` | 不新增額度 | 使用 `ask[0]` 是否為漲停價與量 |
| F4：持倉中漲停板打開出場 | `books` + 下單 API | 不新增行情額度 | 行情沿用原本 `books`；出場送單走交易 API |
| F5：持倉中 1 秒爆量出場 | `trades` | 不新增額度 | 以最近 1 秒 tick volume 累加判斷 |
| F6：委託排隊中爆量取消 | `trades` + 刪單 API | 不新增行情額度 | 取消委託走交易 API |
| F10：委賣價比例 + 即時量確認 | `books` + `trades` | 不新增額度 | `books` 看委賣價；`trades` 看 1 秒量 |
| 下單、成交、委託狀態 | `place_order`、`cancel_order`、`on_order`、`on_filled` | 不屬於行情訂閱 | 預設每日最大交易檔數 5，交易 API 速率一般不是主要瓶頸 |
| 持倉與可用額度更新 | `inventories`、`bank_remain` | 通常不會 | 目前設計為 10 秒 poll 一次 |
| 收盤後預覽明日候選 | REST snapshot / 本地快取 | 通常不會 | 程式會跳過策略引擎與 WebSocket 訂閱 |

## 功能對服務對照

| 功能 | 需要服務 | 說明 |
|---|---|---|
| F1 進場時間與委賣量 | `books` | 判斷漲停價委賣一檔張數 |
| F2 市場選擇 | REST snapshot / 本地篩選 | 決定掃上市、上櫃或兩者 |
| F3 每檔投入金額 | 本地計算 | 不需要行情訂閱 |
| F4 漲停板打開出場 | `books` + 下單 API | 行情判斷後送出賣單 |
| F5 爆量出場 | `trades` | 使用 1 秒成交量 |
| F6 爆量取消委託 | `trades` + 刪單 API | 行情判斷後取消委託 |
| F7 起漲第 N 根 K 以內 | `trades` + 本地狀態；必要時歷史行情 | 盤中用 tick 狀態，快取不足時補查日 K |
| F8 前一日成交量 | REST snapshot | 用 `prev_volume` 篩選候選股 |
| F9 股價區間 | REST snapshot / 本地計算 | 用價格或漲停價篩選 |
| F10 委賣價 + 即時量確認 | `books` + `trades` | 同時使用五檔與成交量 |
| F11 特殊股排除 | REST snapshot | 處置、注意、限當沖旗標 |
| F12 開盤即漲停且當日已賣過封鎖 | `trades/books` + 本地狀態 | 開盤即漲停與賣出狀態需記錄 |
| F13 每日最大成交檔數 | `on_filled` + 本地狀態 | 成交回報累計，不需要行情訂閱 |

## 額度估算

### 正常策略監控

| 候選股檔數 | 訂閱 channel | 保守訂閱數 | 理論需要連線數 | 總額度判斷 |
|---:|---|---:|---:|---|
| 50 | `trades` + `books` | 100 | 1 | 安全 |
| 100 | `trades` + `books` | 200 | 1 | 單連線上限邊界 |
| 150 | `trades` + `books` | 300 | 2 | 需要分片 |
| 200 | `trades` + `books` | 400 | 2 | 安全，已分片 |
| 500 | `trades` + `books` | 1000 | 5 | 到達理論上限，可監控的最大值 |
| 501+ | `trades` + `books` | 1002+ | 6+ | 會超過五連線總額度 |

### REST 使用

| 用途 | 頻率 | 風險 |
|---|---:|---|
| `snapshot.quotes(market='TSE')` | 啟動時約 1 次 | 低 |
| `snapshot.quotes(market='OTC')` | 啟動時約 1 次 | 低 |
| 帳戶 poll | 每 10 秒 | 低 |
| 補查歷史日 K | 最多約 50 檔候選 | 接近歷史行情 60/min，建議控速 |
| fallback 逐支 ticker | 可能 1900+ 次 | 高，容易 429 |

## 建議

1. 正式盤中使用前，建議先用 dry-run 在真實行情環境驗證 101 檔以上會成功建立第 2 至第 5 條 WebSocket。
2. 若未來新增第三個即時 channel，最大股票數會變成 `floor(1000 / 3) = 333`，需同步調整候選股上限。
3. fallback 逐支 ticker 必須控速；更好的做法是強制優先使用 `snapshot.quotes(market=...)` 與本地快取。
4. 補 WebSocket 重連後重新訂閱邏輯，並在重連後用 REST snapshot 或 intraday quote 補最新狀態。
