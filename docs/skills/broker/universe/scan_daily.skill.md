# Skill：選股 `ScanCriteria` + `scan_daily` / `scan_preview_candidates`

## 檔案位置
- `build_win/src/broker/universe.py`

## `ScanCriteria`
```python
@dataclass
class ScanCriteria:
    price_min: Decimal = Decimal("10")
    price_max: Decimal = Decimal("500")
    min_prev_volume: int = 1000
    exclude_disposal: bool = True
    exclude_attention: bool = True
    exclude_day_trade_restricted: bool = True
    markets: Iterable[str] = ("TSE", "OTC")
    max_candidates: int = 100
    max_prior_limit_up_streak: Optional[int] = None  # 0=只追第一根日漲停
```

## `scan_daily(infos, criteria=None) -> List[SymbolInfo]`
- **以「昨收 ± 10%」放寬判斷**，涵蓋所有今天可能進區間 [price_min, price_max] 的標的。
- 過濾條件：市場、價格區間（放寬版）、昨日量、特殊股、`prior_limit_up_streak ≤ max_prior_limit_up_streak`。
- 依昨日量由大到小排序，截斷 `max_candidates`。
- **實際即時價過濾由 engine / GUI 用 `last_price` 動態進行**。

## `scan_preview_candidates(infos, criteria=None) -> List[SymbolInfo]`
- 給「儀錶板預覽」用：以 `resolve_preview_price(info)` (盤中即時報價或昨收) 直接套用 `price_min ~ price_max` 區間，不放寬。
- 其餘條件與 `scan_daily` 相同。

## `resolve_preview_price(info) -> Decimal`
- 盤中：`info.quote_price`；收盤後通常等於當日收盤價。
- 缺報價時：`info.prev_close`。

## 與其他模組關係
- `gui.App._load_dashboard_preview_summary` 透過 `scan_preview_candidates` 算儀錶板列表。
- `engine.replace_universe / start` 透過 `scan_daily` 結果決定要訂閱與監控的標的。
- 條件欄位對應 `TradingConfig.price_min / price_max / blacklist / market_*`。

## 注意事項
- `scan_daily` 故意放寬，避免漏掉盤中價跌出區間又拉回的標的。
- `max_prior_limit_up_streak` 為 None → 不過濾；0 → 只允許今天首日漲停。
- 「處置股 / 注意股 / 限當沖股」三旗標來自 `SymbolInfo` 載入時的欄位。
