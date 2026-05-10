# 全市場前兩個交易日價量 API

> 日期：2026-05-10  
> 方法：GET  
> 範圍：全市場上市 / 上櫃股票最近兩個有日 K 資料的交易日收盤價與成交量

---

## 端點

```http
GET https://stock.try-8verything.com/api/prices/previous-trading-days
```

### Query 參數

| 參數 | 必填 | 說明 | 範例 |
|------|------|------|------|
| `as_of` | 否 | 查詢截止日期，格式為 `YYYY-MM-DD`；未提供時使用台北時區今天 | `2026-05-10` |
| `market` | 否 | 市場篩選；未提供時同時回傳上市與上櫃 | `TWSE` / `TPEX` |

---

## 查詢邏輯

API 會從 `stocks` 取上市 / 上櫃股票，對每一檔股票從 `daily_prices` 查詢 `date <= as_of` 且日期由新到舊的最近 2 筆，再回傳股票名稱、市場別、收盤價與成交量。

因為交易日資料只會在有開盤的日期寫入，週末、國定假日或休市日會自然被略過。若某檔股票資料不足 2 筆，會回傳該檔實際可取得筆數；若查無任何資料，回傳空陣列。

此端點是全市場查詢，不需要前端依股票代號逐檔發 request。

---

## 回應範例

### 200 OK

```json
{
  "as_of": "2026-05-10",
  "count": 2,
  "data": [
    {
      "symbol": "2330",
      "name": "台積電",
      "market": "TWSE",
      "data": [
        {
          "date": "2026-05-08",
          "close": 875,
          "volume": 38214567
        },
        {
          "date": "2026-05-07",
          "close": 868,
          "volume": 29401822
        }
      ]
    },
    {
      "symbol": "6488",
      "name": "環球晶",
      "market": "TPEX",
      "data": [
        {
          "date": "2026-05-08",
          "close": 472.5,
          "volume": 5112000
        },
        {
          "date": "2026-05-07",
          "close": 469,
          "volume": 4389000
        }
      ]
    }
  ]
}
```

### 400 Bad Request

`as_of` 格式錯誤時回傳：

```json
{
  "error": "as_of must be YYYY-MM-DD"
}
```

或 `market` 不是 `TWSE` / `TPEX` 時回傳：

```json
{
  "error": "market must be TWSE or TPEX"
}
```

### 無資料

查無任何符合條件的日 K 價量資料時，仍回傳 `200 OK`：

```json
{
  "as_of": "2026-05-10",
  "count": 0,
  "data": []
}
```

---

## 使用範例

```bash
curl "https://stock.try-8verything.com/api/prices/previous-trading-days"
```

指定截止日期：

```bash
curl "https://stock.try-8verything.com/api/prices/previous-trading-days?as_of=2026-05-10"
```

只查上市：

```bash
curl "https://stock.try-8verything.com/api/prices/previous-trading-days?market=TWSE"
```

只查上櫃：

```bash
curl "https://stock.try-8verything.com/api/prices/previous-trading-days?market=TPEX"
```