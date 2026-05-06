# 富邦新一代 API — 取得所有股票收盤價完整指南

## 概述

富邦新一代 API（FBS TradeAPI）提供台股盤中、快照與歷史行情查詢服務，支援 Python、Node.js、C# SDK。若需取得**所有上市櫃股票**的收盤價，可根據需求選擇以下三種方式：

| 需求 | 建議端點 | 說明 |
|------|---------|------|
| 當日所有股票收盤價（一次取全部）| `snapshot/quotes/{market}` | 最推薦，一次拿整個市場快照 |
| 單一股票當日＋前一交易日收盤 | `historical/stats/{symbol}` | 含近 52 週高低點 |
| 單一股票多日歷史收盤價 | `historical/candles/{symbol}` | 可回溯至 2010 年 |

---

## 初始化 SDK

使用任何端點前，需先登入取得行情權限，並建立行情連線。

### Python

```python
from fubon_neo.sdk import FubonSDK
from fubon_neo.fugle_marketdata.rest.base_rest import FugleAPIError

sdk = FubonSDK()
accounts = sdk.login(
    "Your ID",
    "Your password",
    "Your cert path",
    "Your cert password"
)
sdk.init_realtime()  # 建立行情連線

reststock = sdk.marketdata.rest_client.stock
```

### Node.js

```javascript
const { FubonSDK } = require('fubon-neo');

const sdk = new FubonSDK();
const accounts = sdk.login("Your ID", "Your Password", "Your Cert Path", "Your Cert Password");
sdk.initRealtime();

const stock = sdk.marketdata.restClient.stock;
```

### C#

```csharp
using FubonNeo.Sdk;

var sdk = new FubonSDK();
sdk.Login("Your ID", "Your password", "Your cert path", "Your cert password");
sdk.InitRealtime();

var rest = sdk.MarketData.RestClient.Stock;
```

---

## 方法一：Snapshot Quotes — 一次取得所有股票收盤價（最推薦）

`snapshot/quotes/{market}` 可一次取回整個市場的行情快照，**不需逐一帶入股票代碼**，是批次取得全市場收盤價的最佳方式。

### market 市場別參數

| 參數值 | 說明 |
|--------|------|
| `TSE` | 上市 |
| `OTC` | 上櫃 |
| `ESB` | 興櫃一般板 |
| `TIB` | 臺灣創新板 |
| `PSB` | 興櫃戰略新板 |

### type 標的類型（選填）

| 參數值 | 說明 |
|--------|------|
| `ALLBUT099` | 包含一般股票、特別股及 ETF |
| `COMMONSTOCK` | 僅一般股票 |

### Python 範例：取得上市所有股票收盤價

```python
from fubon_neo.fugle_marketdata.rest.base_rest import FugleAPIError

try:
    # 取得上市全部股票快照
    result = reststock.snapshot.quotes(market='TSE')

    # 取出所有個股收盤價
    for stock in result['data']:
        print(f"{stock['symbol']} {stock['name']} 收盤: {stock.get('closePrice')}")

except FugleAPIError as e:
    print(f"Error: {e}")
    print(f"Status Code: {e.status_code}")
    print(f"Response Text: {e.response_text}")
```

### 一次取得上市＋上櫃所有股票

```python
import time

markets = ['TSE', 'OTC']
all_stocks = []

for market in markets:
    try:
        result = reststock.snapshot.quotes(market=market)
        all_stocks.extend(result['data'])
        time.sleep(0.5)  # 避免超過速率限制
    except FugleAPIError as e:
        print(f"{market} 查詢失敗: {e.status_code}")

# 整理為 dict，方便查詢
close_prices = {
    s['symbol']: {
        'name': s['name'],
        'close': s.get('closePrice'),
        'change': s.get('change'),
        'changePercent': s.get('changePercent')
    }
    for s in all_stocks
}

print(f"共取得 {len(close_prices)} 支股票收盤價")
```

### Response 欄位說明

| 欄位 | 型別 | 說明 |
|------|------|------|
| `date` | string | 日期 |
| `time` | string | 快照時間 |
| `market` | string | 市場別 |
| `data[].symbol` | string | 股票代碼 |
| `data[].name` | string | 股票簡稱 |
| `data[].closePrice` | number | **收盤價** |
| `data[].change` | number | 漲跌金額 |
| `data[].changePercent` | number | 漲跌幅 (%) |
| `data[].tradeVolume` | number | 成交量 |
| `data[].tradeValue` | number | 成交金額 |
| `data[].lastPrice` | number | 最後成交價（含試撮）|
| `data[].isTrial` | bool | 試撮註記 |

---

## 方法二：Historical Stats — 單一股票當日＋前一交易日收盤

`historical/stats/{symbol}` 回傳指定股票的**最後交易日完整行情**，以及前一交易日收盤價與近 52 週高低點。

### Python 範例

```python
try:
    stats = reststock.historical.stats(symbol="2330")
    print(f"最後交易日: {stats['date']}")
    print(f"收盤價: {stats['closePrice']}")
    print(f"前一交易日收盤: {stats['previousClose']}")
    print(f"52 週最高: {stats['week52High']}")
    print(f"52 週最低: {stats['week52Low']}")
except FugleAPIError as e:
    print(f"Error {e.status_code}: {e.response_text}")
```

### Response 欄位說明

| 欄位 | 型別 | 說明 |
|------|------|------|
| `date` | string | 最後交易日日期 |
| `symbol` | string | 股票代碼 |
| `name` | string | 股票簡稱 |
| `closePrice` | number | **最後交易日收盤價** |
| `previousClose` | number | **前一交易日收盤價** |
| `openPrice` | number | 最後交易日開盤價 |
| `highPrice` | number | 最後交易日最高價 |
| `lowPrice` | number | 最後交易日最低價 |
| `change` | number | 漲跌金額 |
| `changePercent` | number | 漲跌幅 (%) |
| `tradeVolume` | number | 成交量 |
| `tradeValue` | number | 成交金額 |
| `week52High` | number | 近 52 週最高價 |
| `week52Low` | number | 近 52 週最低價 |

> ⚠️ **注意**：此端點為單一股票查詢，若要批次查詢所有股票需逐一呼叫，建議搭配速率限制處理（見下方注意事項）。批次取全市場請優先使用**方法一**。

---

## 方法三：Historical Candles — 多日歷史收盤價

`historical/candles/{symbol}` 可取得指定股票的歷史 K 線資料，個股最遠可回溯至 **2010 年**，指數最遠至 **2015 年**。

### 參數說明

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `symbol` | string | ✅ | 股票代碼 |
| `from` | string | — | 開始日期（`yyyy-MM-dd`）|
| `to` | string | — | 結束日期（`yyyy-MM-dd`）|
| `timeframe` | string | — | K 線週期：`1` `5` `10` `15` `30` `60` `D` `W` `M` |
| `fields` | string | — | 欄位：`open,high,low,close,volume,turnover,change` |
| `sort` | string | — | 排序：`desc`（預設）或 `asc` |

> ⚠️ 分 K（`1`、`5`... `60`）無法指定 `from`/`to`，一律回傳**近五日資料**，且不支援 `turnover`、`change` 欄位。

### Python 範例：取得近 5 個交易日收盤價

```python
from datetime import date, timedelta

today = date.today().strftime("%Y-%m-%d")
five_days_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")  # 多抓幾天避開假日

try:
    candles = reststock.historical.candles(**{
        "symbol": "2330",
        "from": five_days_ago,
        "to": today,
        "timeframe": "D",
        "fields": "close,volume,change"
    })

    for day in candles['data']:
        print(f"{day['date']} 收盤: {day['close']} 漲跌: {day.get('change')}")

except FugleAPIError as e:
    print(f"Error {e.status_code}: {e.response_text}")
```

### Response 欄位說明

| 欄位 | 型別 | 說明 |
|------|------|------|
| `symbol` | string | 股票代碼 |
| `timeframe` | string | K 線週期 |
| `data[].date` | string | 日期 |
| `data[].open` | number | 開盤價 |
| `data[].high` | number | 最高價 |
| `data[].low` | number | 最低價 |
| `data[].close` | number | **收盤價** |
| `data[].volume` | number | 成交量 |
| `data[].change` | number | 漲跌金額 |

---

## 批次取得所有股票近幾日收盤價（完整範例）

以下示範結合 `snapshot/quotes` 取得當日收盤，搭配 `historical/candles` 取得近日歷史，並輸出為 CSV。

```python
from fubon_neo.sdk import FubonSDK
from fubon_neo.fugle_marketdata.rest.base_rest import FugleAPIError
from datetime import date, timedelta
import time
import csv

sdk = FubonSDK()
accounts = sdk.login("Your ID", "Your password", "Your cert path", "Your cert password")
sdk.init_realtime()
reststock = sdk.marketdata.rest_client.stock

# Step 1: 取得所有股票代碼（透過 snapshot）
all_symbols = []
for market in ['TSE', 'OTC']:
    try:
        result = reststock.snapshot.quotes(market=market, type='COMMONSTOCK')
        for s in result['data']:
            all_symbols.append({
                'symbol': s['symbol'],
                'name': s['name'],
                'today_close': s.get('closePrice')
            })
        time.sleep(0.5)
    except FugleAPIError as e:
        print(f"{market} 失敗: {e.status_code}")

print(f"共 {len(all_symbols)} 支股票")

# Step 2: 逐一取近 5 日歷史收盤（注意速率限制）
today = date.today().strftime("%Y-%m-%d")
week_ago = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")

rows = []
for i, stock in enumerate(all_symbols[:50]):  # 先測試前 50 支，避免超過速率限制
    try:
        candles = reststock.historical.candles(**{
            "symbol": stock['symbol'],
            "from": week_ago,
            "to": today,
            "timeframe": "D",
            "fields": "close"
        })
        for day in candles.get('data', []):
            rows.append({
                'symbol': stock['symbol'],
                'name': stock['name'],
                'date': day['date'],
                'close': day['close']
            })
        time.sleep(0.2)  # 避免 429 Too Many Requests
    except FugleAPIError as e:
        print(f"{stock['symbol']} 失敗: {e.status_code}")

# Step 3: 輸出 CSV
with open('close_prices.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=['symbol', 'name', 'date', 'close'])
    writer.writeheader()
    writer.writerows(rows)

print("已輸出 close_prices.csv")
```

---

## 注意事項

### 速率限制（Rate Limit）

超過請求速率會收到 `429 Too Many Requests` 回應。建議在迴圈中加入 `time.sleep()` 控制請求頻率：

```python
time.sleep(0.2)  # 每次請求間隔 0.2 秒
```

若仍頻繁遭遇 429，可改用指數退避（exponential backoff）策略：

```python
import time

def safe_request(fn, *args, retries=3, **kwargs):
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except FugleAPIError as e:
            if e.status_code == 429:
                wait = 2 ** i
                print(f"Rate limited, 等待 {wait} 秒後重試...")
                time.sleep(wait)
            else:
                raise
    return None
```

### 大量批次建議策略

| 需求 | 建議做法 |
|------|---------|
| 當日全市場收盤 | 使用 `snapshot/quotes` 一次取得，不需逐一查詢 |
| 歷史多日資料 | 使用 `historical/candles` 帶 `from`/`to` 一次取多日 |
| 全股票歷史批次 | 逐一呼叫 `historical/candles`，加入 `time.sleep(0.2)` 控速 |
| 避免重複呼叫 | 將結果快取至本地 CSV 或資料庫，減少 API 請求次數 |

### 交易時間說明

- **盤中（9:00～13:30）**：`snapshot` 回傳的是即時最新報價，`closePrice` 為盤中最新成交價
- **收盤後**：`snapshot` 與 `historical/stats` 的 `closePrice` 即為當日正式收盤價
- **假日／休市**：`historical/stats` 回傳的是最近一個交易日的資料

---

## 快速選擇指南

```
需要當天全部股票收盤？
  └─ 是 → snapshot/quotes（TSE + OTC）← 最快

需要某支股票前幾天收盤？
  └─ 是 → historical/candles（指定 from/to）

需要某支股票今天＋昨天收盤 + 52週高低點？
  └─ 是 → historical/stats
```
