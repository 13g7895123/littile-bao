# Skill：`SymbolInfoLoader` 系列

## 檔案位置
- `build_win/src/broker/universe.py`

## 抽象
```python
class SymbolInfoLoader:
    def load(self, codes: Iterable[str]) -> Dict[str, SymbolInfo]: ...
```

## `StaticSymbolInfoLoader`
- 接受預先建好的 `Dict[code, SymbolInfo]`。
- `load(codes)` 從中過濾出對應的子集合。
- 由 `MockAdapter` 使用，傳入 `DEFAULT_MOCK_INFOS`。

## `FubonSymbolInfoLoader`
取得真實個股基本資料；分為四種 API：

### A. `fetch_all_codes(markets=("TSE","OTC")) -> List[str]`
- 用 `sdk.marketdata.rest_client.stock.snapshot.quotes(market=...)` 取全市場代碼。
- 兼容多種呼叫簽名：`quotes(market=market)` / `quotes({"market": market})` / `quotes()`。
- 過濾 4 碼純數字代碼，並去重保序。

### B. `load_market_snapshots(markets, *, quote_type="COMMONSTOCK", snapshot_cache=None, cache_snapshots=False) -> Dict[str, SymbolInfo]`
- 一次抓整個市場的 snapshot，包成 `SymbolInfo`。
- 可選擇將快照寫入 `MarketSnapshotCache`，供日後判斷昨日是否收漲停。

### C. `enrich_prior_limit_up_streaks_from_history(infos, *, max_days, max_symbols=50) -> int`
- 對缺少 `prior_limit_up_streak` 的少量候選，呼叫 `historical.candles` 查日 K。
- 比較最近 K 棒與推算漲停價，回算連續收漲停天數。

### D. `load(codes) -> Dict[str, SymbolInfo]`
- 對指定代碼批次抓 ticker；優先 `_try_batch_load`（每 200 支一批），失敗則 `_load_one_by_one`。
- 解析多種欄位名（`closePrice/lastPrice/tradePrice/...`、`previousClose/prevClose/...`）以兼容 SDK 變動。

## `MarketSnapshotCache`
- 路徑：`<project>/cache/market_snapshots.json`
- API：`store_snapshot(infos, snapshot_date, keep_days=20)`、`apply_prior_limit_up_streaks(infos, max_days=2)`、`compute_prior_limit_up_streak(info, max_days=2)`。
- 用於在沒有歷史 K 線時，從每日盤後快照推算「昨日是否曾收漲停 / 連續多少天」。

## `PreviousTradingDaysApiClient` + `PreviousTradingDaysCache`
- 對外 API：`https://stock.try-8verything.com/api/prices/previous-trading-days`
- 提供開盤前載入「昨日 + 前日」價量，無需登入 SDK 即可建出 `SymbolInfo`。
- `load_symbol_infos(markets, as_of="")` 回 `Dict[code, SymbolInfo]`，並在 `cache` 中保留 payload 供下次使用。

## 注意事項
- SDK 欄位名常變，加新欄位時優先用「多 alias 試一輪」的策略（參考 `_parse_item`）。
- 4 碼代碼過濾在 `fetch_all_codes` 與 `_parse_item` 內，避免抓到權證 / ETF 變體。
- 對外 API URL 寫死在 `PREVIOUS_TRADING_DAYS_API_URL`；若變動請在常數一處改即可。

## 對應測試
- `build_win/src/tests/test_universe.py`
