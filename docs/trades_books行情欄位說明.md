# `trades` 與 `books` 行情欄位說明

日期：2026-05-09

## 總覽

`trades` 與 `books` 是兩個不同的即時行情 channel。盤中策略同時訂閱兩者時，會得到兩種互補資料：

| Channel | 中文意義 | 主要回答的問題 | 本專案主要用途 |
|---|---|---|---|
| `trades` | 逐筆成交 / Tick | 最新成交價是多少？這一筆成交多少量？最近 1 秒成交量多少？ | 漲停觸發、價格/漲跌、1 秒量、爆量出場/取消 |
| `books` | 即時五檔 / Order book | 委買委賣排隊狀態如何？漲停價委賣還有多少？板子是否打開？ | 漲停委賣張數、委賣價確認、漲停板打開判斷 |

兩者共同會有股票代號與事件時間；但 `trades` 不提供完整五檔，`books` 也不代表真實成交量。策略需要兩者一起使用，才可以同時判斷「成交是否打到漲停」與「漲停價排隊狀態」。

## `trades` 包含的資訊

### 本專案標準化後的欄位

`build_win/src/broker/models.py` 目前將 `trades` 標準化為 `TickEvent`：

| 標準欄位 | 型別 | 說明 | 策略用途 |
|---|---|---|---|
| `code` | `str` | 股票代號，例如 `2330` | 對應個股狀態 |
| `time` | `datetime` | 事件時間 | 目前以本機收到訊息時間為主 |
| `price` | `Decimal` | 最新成交價 | 判斷是否達漲停、顯示現價、計算漲跌 |
| `volume` | `int` | 本筆成交量 | 累加最近 1 秒成交量 |
| `cum_volume` | `int` | 當日累積成交量 | 輔助觀察；目前策略核心主要用 `volume` |
| `prev_close` | `Optional[Decimal]` | 昨日收盤價 / 參考價 | 計算漲跌與漲跌幅 |

### 目前 parser 支援的原始欄位名稱

富邦 SDK 或不同版本推送格式可能不同，因此 `FubonRealtimeFeed._to_tick()` 做了容錯：

| 標準欄位 | 支援的原始 key |
|---|---|
| `code` | `symbol`、`code` |
| `price` | `price`、`lastPrice`、`closePrice`、`matchPrice` |
| `volume` | `size`、`volume`、`lastSize`、`qty` |
| `cum_volume` | `total`、`cum_volume`、`totalVolume`、`accVolume` |
| `prev_close` | `prev_close`、`previousClose`、`referencePrice` |

判斷是否為 `trades` 訊息的條件包含：

| 判斷方式 | 說明 |
|---|---|
| `event` 是 `trades` 或 `trade` | 直接視為成交資料 |
| `type` 是 `trade` 或 `trades` | 直接視為成交資料 |
| payload 同時有價格與成交量欄位，且沒有 `ask/bid` | 視為成交資料 |

### 範例

```json
{
  "event": "data",
  "data": {
    "symbol": "2330",
    "type": "trade",
    "price": 1100.0,
    "size": 50,
    "total": 1200,
    "previousClose": 1000.0
  }
}
```

標準化後：

```json
{
  "code": "2330",
  "price": 1100.0,
  "volume": 50,
  "cum_volume": 1200,
  "prev_close": 1000.0
}
```

## `books` 包含的資訊

### 本專案標準化後的欄位

`build_win/src/broker/models.py` 目前將 `books` 標準化為 `BookEvent`：

| 標準欄位 | 型別 | 說明 | 策略用途 |
|---|---|---|---|
| `code` | `str` | 股票代號 | 對應個股狀態 |
| `time` | `datetime` | 事件時間 | 目前以本機收到訊息時間為主 |
| `ask` | `list[BookLevel]` | 委賣價量陣列，`ask[0]` 是最佳賣價 | 判斷漲停價委賣張數、委賣價條件 |
| `bid` | `list[BookLevel]` | 委買價量陣列，`bid[0]` 是最佳買價 | 輔助判斷買方排隊與板是否仍封住 |

每一筆 `BookLevel`：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `price` | `Decimal` | 該檔價格 |
| `volume` | `int` | 該檔委託量 |

### 目前 parser 支援的原始欄位名稱

| 標準欄位 | 支援的原始 key |
|---|---|
| `code` | `symbol`、`code` |
| `ask` 陣列 | `asks`、`ask` |
| `bid` 陣列 | `bids`、`bid` |
| 單檔 ask | `askPrice` / `ask_price` 搭配 `askSize` / `ask_size` / `askVolume` |
| 單檔 bid | `bidPrice` / `bid_price` 搭配 `bidSize` / `bid_size` / `bidVolume` |
| level 價格 | `price`、`p` |
| level 量 | `size`、`volume`、`v` |

判斷是否為 `books` 訊息的條件包含：

| 判斷方式 | 說明 |
|---|---|
| `event` 是 `books`、`book` 或 `snapshot` | 視為五檔資料 |
| payload 包含 `asks/bids` 或 `ask/bid` | 視為五檔資料 |

### 範例

```json
{
  "event": "data",
  "data": {
    "symbol": "2330",
    "asks": [
      {"price": 1100.0, "size": 320},
      {"price": 1099.0, "size": 150}
    ],
    "bids": [
      {"price": 1099.0, "size": 88},
      {"price": 1098.0, "size": 120}
    ]
  }
}
```

標準化後：

```json
{
  "code": "2330",
  "ask": [
    {"price": 1100.0, "volume": 320},
    {"price": 1099.0, "volume": 150}
  ],
  "bid": [
    {"price": 1099.0, "volume": 88},
    {"price": 1098.0, "volume": 120}
  ]
}
```

## 同時訂閱後可得到的策略資訊

| 策略需要的資訊 | 來源 | 計算方式 |
|---|---|---|
| 最新成交價 | `trades.price` | 直接取最新 tick price |
| 漲跌 | `trades.price` + `prev_close` | `price - prev_close` |
| 漲跌幅 | `trades.price` + `prev_close` | `(price - prev_close) / prev_close * 100` |
| 是否打到漲停 | `trades.price` + `limit_up_price` | `price >= limit_up_price` |
| 1 秒成交量 | `trades.volume` | 最近 1 秒 tick volume 滑動加總 |
| 漲停價委賣張數 | `books.ask[0]` + `limit_up_price` | 若 `ask[0].price == limit_up_price`，取 `ask[0].volume`，否則 0 |
| 委賣價比例條件 | `books.ask[0].price` | 與 `limit_up_price * ask_price_ratio` 比較 |
| 漲停板是否打開 | `books.ask[0]` + 內部狀態 | 曾在漲停狀態後，若 `ask[0]` 不再是漲停價，視為板打開 |
| 持倉現價 | `trades.price` 或帳戶庫存 last price | 儀表板與損益顯示使用 |

## 目前實作限制

1. `time` 目前使用本機接收時間 `datetime.now()`，沒有保留 SDK 原始成交時間或五檔時間。
2. `trades` 目前只保留價格、量、累計量、昨收；若 SDK 原始訊息有成交序號、買賣別、交易所、盤別等欄位，尚未存入 DTO。
3. `books` 目前只保留委買/委賣價量；若 SDK 原始訊息有每檔委託筆數、交易所時間、狀態碼等欄位，尚未存入 DTO。
4. `books` 的推送有時可能是 snapshot，有時可能是 data 更新；目前 parser 只要看見 `ask/bid` 結構就轉成 `BookEvent`。
5. 上線前建議在真實盤中將原始 WebSocket payload 落地成 JSONL，確認富邦 SDK v2.2.8 的實際欄位名稱與目前 parser 完全相容。

## 對打板策略的最小必要欄位

| 目的 | 最小欄位 |
|---|---|
| 漲停觸發 | `trades.code`、`trades.price`、`limit_up_price` |
| 1 秒爆量 | `trades.code`、`trades.volume`、事件接收時間 |
| 委賣張數門檻 | `books.code`、`books.ask[0].price`、`books.ask[0].volume`、`limit_up_price` |
| 委賣價比例 | `books.ask[0].price`、`limit_up_price`、`ask_price_ratio` |
| 板打開出場 | `books.ask[0].price`、內部 `is_at_limit_up` 狀態 |
| 儀表板價格與漲跌 | `trades.price`、`prev_close` |
