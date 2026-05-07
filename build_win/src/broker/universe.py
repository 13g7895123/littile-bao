"""
broker.universe — 個股基本資料 / 開盤前選股

Milestone 3：提供 SymbolInfo 載入（昨收 / 漲停價 / 特殊股標記）
Milestone 6：scan_daily() 全市場掃描（待實作）
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Optional, Sequence


# ─────────────────────────────────────────────────────────
#  DTO
# ─────────────────────────────────────────────────────────

@dataclass
class SymbolInfo:
    """個股基本資料（開盤前一次性載入）。"""
    code: str
    name: str
    market: str  # TSE / OTC
    prev_close: Decimal
    quote_price: Optional[Decimal]
    limit_up_price: Decimal
    limit_down_price: Decimal
    prev_volume: int = 0
    is_disposal: bool = False
    is_attention: bool = False
    is_day_trade_restricted: bool = False
    open_limit_up: bool = False  # 開盤後首筆 tick 才能確認，預設 False
    prior_limit_up_streak: Optional[int] = None  # 昨日起往前連續收漲停天數；None=資料不足


# ─────────────────────────────────────────────────────────
#  漲跌停價計算（依台股規則：±10%，依價格區間 round 至 tick）
# ─────────────────────────────────────────────────────────

# 台股股價 tick 表（價格上限：tick）
_TICK_TABLE = [
    (Decimal("10"),    Decimal("0.01")),
    (Decimal("50"),    Decimal("0.05")),
    (Decimal("100"),   Decimal("0.1")),
    (Decimal("500"),   Decimal("0.5")),
    (Decimal("1000"),  Decimal("1")),
    (Decimal("9999999"), Decimal("5")),
]


def tick_size(price: Decimal) -> Decimal:
    """依台股最小升降單位表回傳 tick。"""
    for upper, tick in _TICK_TABLE:
        if price < upper:
            return tick
    return Decimal("5")


def round_to_tick(price: Decimal, *, mode: str = "down") -> Decimal:
    """
    將價格四捨五入至最接近的 tick。
    - mode='down'：跌停（無條件捨去至上一個 tick）
    - mode='up'  ：漲停（無條件進位至下一個 tick）
    - mode='near'：四捨五入
    """
    t = tick_size(price)
    if mode == "down":
        return (price / t).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * t \
            if False else (price // t) * t
    if mode == "up":
        # 進位：若已是 tick 倍數則保持
        q = (price // t) * t
        return q if q == price else q + t
    return (price / t).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * t


def calc_limit_up(prev_close: Decimal) -> Decimal:
    """漲停價 = 昨收 × 1.1，依 tick 無條件捨去（保守，避免超出實際漲停）。"""
    raw = prev_close * Decimal("1.1")
    t = tick_size(raw)
    return (raw // t) * t


def calc_limit_down(prev_close: Decimal) -> Decimal:
    """跌停價 = 昨收 × 0.9，依 tick 無條件進位（保守）。"""
    raw = prev_close * Decimal("0.9")
    t = tick_size(raw)
    q = (raw // t) * t
    return q if q == raw else q + t


def is_limit_up_close(close: Decimal, prev_close: Decimal) -> bool:
    """判斷某日收盤是否為以前一交易日收盤推算出的漲停價。"""
    try:
        close_dec = Decimal(str(close))
        prev_dec = Decimal(str(prev_close))
    except Exception:
        return False
    if close_dec <= 0 or prev_dec <= 0:
        return False
    return close_dec == calc_limit_up(prev_dec)


def _default_snapshot_cache_path() -> str:
    if getattr(__import__("sys"), "frozen", False):
        base = os.path.dirname(__import__("sys").executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "cache", "market_snapshots.json")


class MarketSnapshotCache:
    """本地全市場收盤快照快取，用於開盤前判斷昨日是否已收漲停。"""

    def __init__(self, path: str = "") -> None:
        self.path = path or _default_snapshot_cache_path()
        self._snapshots: Dict[str, Dict[str, dict]] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            snapshots = raw.get("snapshots", {}) if isinstance(raw, dict) else {}
            if isinstance(snapshots, dict):
                self._snapshots = {
                    str(day): records
                    for day, records in snapshots.items()
                    if isinstance(records, dict)
                }
        except Exception:
            self._snapshots = {}

    def save(self, *, keep_days: int = 20) -> None:
        dates = self._ordered_dates()
        if keep_days > 0 and len(dates) > keep_days:
            keep = set(dates[-keep_days:])
            self._snapshots = {
                day: records for day, records in self._snapshots.items()
                if day in keep
            }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {"version": 1, "snapshots": self._snapshots}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)

    def store_snapshot(
        self,
        infos: Iterable[SymbolInfo],
        snapshot_date: str,
        *,
        keep_days: int = 20,
    ) -> int:
        day = self._normalize_date(snapshot_date)
        if not day:
            return 0
        records: Dict[str, dict] = {}
        for info in infos:
            close_price = info.quote_price
            if close_price is None or close_price <= 0:
                continue
            records[info.code] = {
                "code": info.code,
                "name": info.name,
                "market": info.market,
                "prev_close": str(info.prev_close),
                "close": str(close_price),
                "prev_volume": int(info.prev_volume or 0),
                "is_disposal": bool(info.is_disposal),
                "is_attention": bool(info.is_attention),
                "is_day_trade_restricted": bool(info.is_day_trade_restricted),
            }
        if not records:
            return 0
        self._snapshots[day] = records
        self.save(keep_days=keep_days)
        return len(records)

    def apply_prior_limit_up_streaks(
        self,
        infos: Iterable[SymbolInfo],
        *,
        max_days: int = 2,
    ) -> int:
        updated = 0
        for info in infos:
            streak = self.compute_prior_limit_up_streak(info, max_days=max_days)
            if streak is not None:
                info.prior_limit_up_streak = streak
                updated += 1
        return updated

    def compute_prior_limit_up_streak(
        self,
        info: SymbolInfo,
        *,
        max_days: int = 2,
    ) -> Optional[int]:
        if max_days <= 0:
            return 0
        dates = self._ordered_dates()
        if not dates:
            return None

        start_idx = self._find_previous_trading_index(info, dates)
        if start_idx is None:
            return None

        streak = 0
        idx = start_idx
        while idx >= 0 and streak < max_days:
            record = self._snapshots.get(dates[idx], {}).get(info.code)
            if not record:
                break
            close_price = self._record_decimal(record, "close")
            prev_close = self._record_decimal(record, "prev_close")
            if close_price is None or prev_close is None:
                break
            if not is_limit_up_close(close_price, prev_close):
                break
            streak += 1
            idx -= 1
        return streak

    def _find_previous_trading_index(
        self,
        info: SymbolInfo,
        dates: Sequence[str],
    ) -> Optional[int]:
        for idx in range(len(dates) - 1, -1, -1):
            record = self._snapshots.get(dates[idx], {}).get(info.code)
            if not record:
                continue
            close_price = self._record_decimal(record, "close")
            if close_price is not None and close_price == info.prev_close:
                return idx
        return None

    def _ordered_dates(self) -> List[str]:
        return sorted(self._snapshots.keys())

    @staticmethod
    def _record_decimal(record: dict, key: str) -> Optional[Decimal]:
        raw = record.get(key)
        if raw in (None, "", "-"):
            return None
        try:
            value = Decimal(str(raw))
        except Exception:
            return None
        return value if value > 0 else None

    @classmethod
    def _normalize_date(cls, value) -> str:
        if value in (None, "", "-"):
            return ""
        text = str(value).strip().replace("/", "-")
        if len(text) >= 10:
            text = text[:10]
        if len(text) == 8 and text.isdigit():
            text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        try:
            return date.fromisoformat(text).isoformat()
        except Exception:
            return ""


# ─────────────────────────────────────────────────────────
#  載入器
# ─────────────────────────────────────────────────────────

def build_symbol_info(
    code: str,
    name: str,
    market: str,
    prev_close: float | Decimal,
    *,
    quote_price: float | Decimal | None = None,
    prev_volume: int = 0,
    is_disposal: bool = False,
    is_attention: bool = False,
    is_day_trade_restricted: bool = False,
    prior_limit_up_streak: Optional[int] = None,
) -> SymbolInfo:
    """以昨收價自動算出漲跌停。"""
    pc = Decimal(str(prev_close))
    qp: Optional[Decimal] = None
    if quote_price not in (None, ""):
        try:
            qp = Decimal(str(quote_price))
        except Exception:
            qp = None
        if qp is not None and qp <= 0:
            qp = None
    return SymbolInfo(
        code=code,
        name=name,
        market=market,
        prev_close=pc,
        quote_price=qp,
        limit_up_price=calc_limit_up(pc),
        limit_down_price=calc_limit_down(pc),
        prev_volume=prev_volume,
        is_disposal=is_disposal,
        is_attention=is_attention,
        is_day_trade_restricted=is_day_trade_restricted,
        prior_limit_up_streak=prior_limit_up_streak,
    )


class SymbolInfoLoader:
    """SymbolInfo 載入器抽象介面。"""

    def load(self, codes: Iterable[str]) -> Dict[str, SymbolInfo]:
        raise NotImplementedError


class StaticSymbolInfoLoader(SymbolInfoLoader):
    """直接吃預先建好的 SymbolInfo dict（Mock / 測試用）。"""

    def __init__(self, infos: Dict[str, SymbolInfo]) -> None:
        self._infos = infos

    def load(self, codes: Iterable[str]) -> Dict[str, SymbolInfo]:
        out: Dict[str, SymbolInfo] = {}
        for c in codes:
            if c in self._infos:
                out[c] = self._infos[c]
        return out


class FubonSymbolInfoLoader(SymbolInfoLoader):
    """
    透過 fubon_neo SDK 取得個股基本資料。

    主要流程：
      1. fetch_all_codes()  — 呼叫 snapshot 取得全市場代碼清單
      2. load(codes)        — 依代碼清單批次取得 ticker（prevClose / 特殊股標記）
    """

    def __init__(self, adapter) -> None:
        self._adapter = adapter

    # ── 取得全市場代碼清單 ──────────────────────────────────

    def fetch_all_codes(self, markets: Iterable[str] = ("TSE", "OTC")) -> List[str]:
        """
        從 Fubon marketdata REST API 取得全市場股票代碼。

        嘗試路徑：
          sdk.marketdata.rest_client.stock.snapshot.quotes(market=market)
          → items[].symbol
        回傳去重後的代碼清單。
        """
        # 若傳入空市場清單，預設取兩個市場
        markets = list(markets) or ["TSE", "OTC"]
        try:
            sdk = self._adapter.sdk
        except Exception:
            return []
        self._ensure_marketdata_ready(sdk)

        rest = self._resolve_rest_stock(sdk)
        if rest is None:
            return []

        codes: List[str] = []
        for market in markets:
            try:
                snapshot = getattr(rest, "snapshot", None)
                quotes_fn = getattr(snapshot, "quotes", None) if snapshot else None
                if not callable(quotes_fn):
                    continue

                # 嘗試各種 API 呼叫方式
                try:
                    res = quotes_fn(market=market)
                except TypeError:
                    try:
                        res = quotes_fn({"market": market})
                    except Exception:
                        res = quotes_fn()

                # 解析回傳值
                items = None
                if isinstance(res, dict):
                    items = res.get("data") or res.get("items") or res.get("quotes") or []
                elif hasattr(res, "data"):
                    items = res.data or []
                elif isinstance(res, list):
                    items = res

                if not items:
                    continue

                for item in items:
                    if isinstance(item, dict):
                        sym = item.get("symbol") or item.get("code") or item.get("stock_no")
                    else:
                        sym = (getattr(item, "symbol", None)
                               or getattr(item, "code", None)
                               or getattr(item, "stock_no", None))
                    if sym and str(sym).isdigit() and len(str(sym)) == 4:
                        codes.append(str(sym))

            except Exception as e:
                print(f"[Universe] fetch_all_codes market={market} 失敗：{e}")

        # 去重保序
        seen: set = set()
        result = []
        for c in codes:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return result

    def load_market_snapshots(
        self,
        markets: Iterable[str] = ("TSE", "OTC"),
        *,
        quote_type: str = "COMMONSTOCK",
        snapshot_cache: Optional[MarketSnapshotCache] = None,
        cache_snapshots: bool = False,
    ) -> Dict[str, SymbolInfo]:
        """用 snapshot.quotes(market=...) 一次載入整個市場快照。"""
        markets = list(markets) or ["TSE", "OTC"]
        try:
            sdk = self._adapter.sdk
        except Exception:
            return {}
        self._ensure_marketdata_ready(sdk)

        rest = self._resolve_rest_stock(sdk)
        if rest is None:
            return {}

        out: Dict[str, SymbolInfo] = {}
        for market in markets:
            items, snapshot_date = self._fetch_market_snapshot(
                rest, market, quote_type=quote_type)
            market_infos: List[SymbolInfo] = []
            for item in items:
                si = self._parse_item(item, fallback_market=market)
                if si:
                    out[si.code] = si
                    market_infos.append(si)
            if cache_snapshots and snapshot_cache is not None and snapshot_date:
                snapshot_cache.store_snapshot(market_infos, snapshot_date)
        return out

    def enrich_prior_limit_up_streaks_from_history(
        self,
        infos: Iterable[SymbolInfo],
        *,
        max_days: int,
        max_symbols: int = 50,
    ) -> int:
        """快取不足時，僅針對少量候選股補抓日 K 判斷昨日起連續漲停。"""
        if max_days <= 0 or max_symbols <= 0:
            return 0
        try:
            sdk = self._adapter.sdk
        except Exception:
            return 0
        self._ensure_marketdata_ready(sdk)
        rest = self._resolve_rest_stock(sdk)
        if rest is None:
            return 0

        historical = getattr(rest, "historical", None)
        candles_fn = getattr(historical, "candles", None) if historical else None
        if not callable(candles_fn):
            return 0

        updated = 0
        to_date = date.today().isoformat()
        from_date = (date.today() - timedelta(days=max(14, max_days * 7))).isoformat()
        for info in list(infos)[:max_symbols]:
            if info.prior_limit_up_streak is not None:
                continue
            data = self._fetch_daily_candles(
                candles_fn, info.code, from_date=from_date, to_date=to_date)
            streak = self._compute_streak_from_candles(
                data, info.prev_close, max_days=max_days)
            if streak is not None:
                info.prior_limit_up_streak = streak
                updated += 1
        return updated

    # ── 批次取得個股 SymbolInfo ──────────────────────────────

    def load(self, codes: Iterable[str]) -> Dict[str, SymbolInfo]:
        try:
            sdk = self._adapter.sdk
        except Exception:
            return {}
        self._ensure_marketdata_ready(sdk)

        out: Dict[str, SymbolInfo] = {}
        rest = self._resolve_rest_stock(sdk)
        if rest is None:
            return {}

        code_list = list(codes)

        # 優先嘗試批次 snapshot（一次取全部，效能最好）
        batch_ok = self._try_batch_load(rest, code_list, out)
        if not batch_ok:
            # 退回逐筆查詢
            self._load_one_by_one(rest, code_list, out)

        return out

    def _try_batch_load(self, rest, codes: List[str], out: Dict[str, SymbolInfo]) -> bool:
        """嘗試用 snapshot.quotes(symbols=[...]) 批次取得，成功回傳 True。"""
        try:
            snapshot = getattr(rest, "snapshot", None)
            quotes_fn = getattr(snapshot, "quotes", None) if snapshot else None
            if not callable(quotes_fn):
                return False

            # 分批 200 支
            for i in range(0, len(codes), 200):
                chunk = codes[i:i + 200]
                try:
                    res = quotes_fn(symbols=chunk)
                except TypeError:
                    try:
                        res = quotes_fn({"symbols": chunk})
                    except Exception:
                        return False

                items = None
                if isinstance(res, dict):
                    items = res.get("data") or res.get("items") or []
                elif hasattr(res, "data"):
                    items = res.data or []
                elif isinstance(res, list):
                    items = res

                if not items:
                    continue

                for item in items:
                    si = self._parse_item(item)
                    if si:
                        out[si.code] = si

            return True
        except Exception:
            return False

    def _load_one_by_one(self, rest, codes: List[str], out: Dict[str, SymbolInfo]) -> None:
        """逐筆查 intraday.ticker（備援）。"""
        for code in codes:
            try:
                raw = self._fetch_ticker(rest, code)
                if not raw:
                    continue
                si = self._parse_item(raw, fallback_code=code)
                if si:
                    out[si.code] = si
            except Exception as e:
                print(f"[Universe] 載入 {code} 失敗：{e}")

    def _parse_item(self, raw, fallback_code: str = "",
                    fallback_market: str = "") -> Optional["SymbolInfo"]:
        """將 API 回傳的 dict / object 轉為 SymbolInfo。"""
        if isinstance(raw, dict):
            g = raw.get
        else:
            def g(k, d=None):
                return getattr(raw, k, d)

        code = str(g("symbol") or g("code") or g("stock_no") or fallback_code)
        if not code:
            return None

        quote_price = self._decimal_from_fields(
            g,
            "closePrice", "close_price", "closingPrice", "close",
            "lastPrice", "last_price", "latestPrice",
            "tradePrice", "trade_price", "matchPrice", "match_price",
            "currentPrice", "current_price", "price",
        )

        pc_raw = (g("previousClose") or g("prevClose")
                  or g("referencePrice") or g("prev_close") or 0)
        if (not pc_raw or str(pc_raw) in ("0", "0.0")) and quote_price is not None:
            change = self._decimal_from_fields(
                g, "change", "priceChange", "changePrice",
                positive_only=False)
            if change is not None:
                pc_raw = quote_price - change
        try:
            pc = Decimal(str(pc_raw))
        except Exception:
            return None
        if pc <= 0:
            return None

        market_raw = str(g("market") or g("exchange") or fallback_market or "TSE")
        market_upper = market_raw.upper()
        market_lower = market_raw.lower()
        market = "OTC" if "OTC" in market_upper or "TPEX" in market_upper or "tpex" in market_lower else "TSE"

        prev_vol = 0
        try:
            prev_vol = int(
                g("previousVolume") or g("prevVolume") or g("prev_volume")
                or g("tradeVolume") or g("totalVolume") or g("volume") or 0
            )
        except Exception:
            pass

        return build_symbol_info(
            code=code,
            name=str(g("name") or g("stock_name") or code),
            market=market,
            prev_close=pc,
            quote_price=quote_price,
            prev_volume=prev_vol,
            is_disposal=bool(g("isDisposition") or g("isDisposal") or g("is_disposal")),
            is_attention=bool(g("isAttention") or g("is_attention")),
            is_day_trade_restricted=bool(
                g("isDayTradeRestricted") or g("is_day_trade_restricted")
            ),
        )

    @classmethod
    def _compute_streak_from_candles(
        cls,
        candles: List[tuple[str, Decimal]],
        current_prev_close: Decimal,
        *,
        max_days: int,
    ) -> Optional[int]:
        if not candles or max_days <= 0:
            return None
        candles = sorted(candles, key=lambda item: item[0])
        start_idx: Optional[int] = None
        for idx in range(len(candles) - 1, -1, -1):
            if candles[idx][1] == current_prev_close:
                start_idx = idx
                break
        if start_idx is None or start_idx <= 0:
            return None
        streak = 0
        idx = start_idx
        while idx > 0 and streak < max_days:
            close_price = candles[idx][1]
            prev_close = candles[idx - 1][1]
            if not is_limit_up_close(close_price, prev_close):
                break
            streak += 1
            idx -= 1
        return streak

    @staticmethod
    def _decimal_from_fields(getter, *names: str,
                             positive_only: bool = True) -> Optional[Decimal]:
        for name in names:
            raw = getter(name)
            if raw in (None, "", "-"):
                continue
            try:
                value = Decimal(str(raw))
            except Exception:
                continue
            if not positive_only or value > 0:
                return value
        return None

    @staticmethod
    def _resolve_rest_stock(sdk):
        md = getattr(sdk, "marketdata", None)
        rc = getattr(md, "rest_client", None) if md else None
        return getattr(rc, "stock", None) if rc else None

    @staticmethod
    def _ensure_marketdata_ready(sdk) -> None:
        if getattr(sdk, "_stock_trader_marketdata_ready", False):
            return
        init_realtime = getattr(sdk, "init_realtime", None)
        if not callable(init_realtime):
            return
        try:
            init_realtime()
            try:
                setattr(sdk, "_stock_trader_marketdata_ready", True)
            except Exception:
                pass
        except Exception:
            pass

    @staticmethod
    def _extract_items(res):
        if isinstance(res, dict):
            return res.get("data") or res.get("items") or res.get("quotes") or []
        if hasattr(res, "data"):
            return res.data or []
        if isinstance(res, list):
            return res
        return []

    @classmethod
    def _fetch_market_snapshot_items(cls, rest, market: str,
                                     *, quote_type: str = "") -> list:
        items, _snapshot_date = cls._fetch_market_snapshot(
            rest, market, quote_type=quote_type)
        return items

    @classmethod
    def _fetch_market_snapshot(cls, rest, market: str,
                               *, quote_type: str = "") -> tuple[list, str]:
        snapshot = getattr(rest, "snapshot", None)
        quotes_fn = getattr(snapshot, "quotes", None) if snapshot else None
        if not callable(quotes_fn):
            return [], ""

        attempts = []
        if quote_type:
            attempts.extend([
                lambda: quotes_fn(market=market, type=quote_type),
                lambda: quotes_fn({"market": market, "type": quote_type}),
            ])
        attempts.extend([
            lambda: quotes_fn(market=market),
            lambda: quotes_fn({"market": market}),
            lambda: quotes_fn(),
        ])

        for attempt in attempts:
            try:
                res = attempt()
                items = cls._extract_items(res)
                if items:
                    return items, cls._extract_snapshot_date(res, items)
            except TypeError:
                continue
            except Exception as exc:
                print(f"[Universe] snapshot market={market} 失敗：{exc}")
                return [], ""
        return [], ""

    @staticmethod
    def _extract_snapshot_date(res, items: list) -> str:
        raw = None
        if isinstance(res, dict):
            raw = (res.get("date") or res.get("snapshotDate")
                   or res.get("tradeDate"))
        elif hasattr(res, "date"):
            raw = getattr(res, "date", None)
        if not raw and items:
            first = items[0]
            if isinstance(first, dict):
                raw = first.get("date") or first.get("tradeDate")
            else:
                raw = getattr(first, "date", None) or getattr(first, "tradeDate", None)
        return MarketSnapshotCache._normalize_date(raw)

    @staticmethod
    def _fetch_daily_candles(candles_fn, code: str,
                             *, from_date: str, to_date: str) -> List[tuple[str, Decimal]]:
        params = {
            "symbol": code,
            "from": from_date,
            "to": to_date,
            "timeframe": "D",
            "fields": "close",
            "sort": "asc",
        }
        try:
            res = candles_fn(**params)
        except TypeError:
            try:
                res = candles_fn(params)
            except TypeError:
                res = candles_fn(code)
        items = FubonSymbolInfoLoader._extract_items(res)
        out: List[tuple[str, Decimal]] = []
        for item in items:
            if isinstance(item, dict):
                raw_date = item.get("date") or item.get("tradeDate")
                raw_close = item.get("close") or item.get("closePrice")
            else:
                raw_date = getattr(item, "date", None) or getattr(item, "tradeDate", None)
                raw_close = getattr(item, "close", None) or getattr(item, "closePrice", None)
            day = MarketSnapshotCache._normalize_date(raw_date)
            if not day or raw_close in (None, "", "-"):
                continue
            try:
                close_price = Decimal(str(raw_close))
            except Exception:
                continue
            if close_price > 0:
                out.append((day, close_price))
        return out

    @staticmethod
    def _fetch_ticker(rest, code: str) -> Optional[dict]:
        intraday = getattr(rest, "intraday", None)
        if intraday is None:
            return None
        ticker = getattr(intraday, "ticker", None)
        if not callable(ticker):
            return None
        try:
            res = ticker(symbol=code)
        except TypeError:
            res = ticker(code)
        if isinstance(res, dict):
            return res
        return getattr(res, "data", None) or getattr(res, "__dict__", None)


# ─────────────────────────────────────────────────────────
#  Mock 預設清單（與舊 engine.MOCK_STOCKS 一致）
# ─────────────────────────────────────────────────────────

DEFAULT_MOCK_INFOS: List[SymbolInfo] = [
    build_symbol_info("2330", "台積電",   "TSE", 1000.0),
    build_symbol_info("2317", "鴻海",     "TSE",  200.0, is_attention=True),
    build_symbol_info("3008", "大立光",   "TSE", 2600.0),
    build_symbol_info("2454", "聯發科",   "TSE", 1300.0, is_disposal=True),
    build_symbol_info("6505", "台塑化",   "TSE",   98.2, is_day_trade_restricted=True),
    build_symbol_info("6669", "緯穎",     "OTC", 2850.0),
    build_symbol_info("4919", "新唐",     "OTC",  210.0),
    build_symbol_info("2382", "廣達",     "TSE",  305.0),
    build_symbol_info("3711", "日月光投", "TSE",  136.5),
    build_symbol_info("2603", "長榮",     "TSE",  184.0),
]
# 開盤即漲停 demo
for _info in DEFAULT_MOCK_INFOS:
    if _info.code == "4919":
        _info.open_limit_up = True


# ─────────────────────────────────────────────────────────
#  動態選股（Milestone 6）
# ─────────────────────────────────────────────────────────

@dataclass
class ScanCriteria:
    """開盤前 / 盤中動態選股條件。"""
    price_min: Decimal = Decimal("10")     # 股價下限（漲停價）
    price_max: Decimal = Decimal("500")    # 股價上限（漲停價）
    min_prev_volume: int = 1000            # 昨日成交量下限（張）
    exclude_disposal: bool = True          # 排除處置股
    exclude_attention: bool = True         # 排除注意股
    exclude_day_trade_restricted: bool = True  # 排除限當沖
    markets: Iterable[str] = ("TSE", "OTC")
    max_candidates: int = 100
    max_prior_limit_up_streak: Optional[int] = None  # 0=只追第一根日漲停；1=第二根以內


def scan_daily(
    infos: Iterable[SymbolInfo],
    criteria: Optional[ScanCriteria] = None,
) -> List[SymbolInfo]:
    """從 infos（通常為全市場 SymbolInfo）篩出符合條件的候選清單。"""
    crit = criteria or ScanCriteria()
    markets = set(crit.markets)
    out: List[SymbolInfo] = []
    for si in infos:
        if si.market not in markets:
            continue
        if not (crit.price_min <= si.limit_up_price <= crit.price_max):
            continue
        if si.prev_volume < crit.min_prev_volume:
            continue
        if crit.exclude_disposal and si.is_disposal:
            continue
        if crit.exclude_attention and si.is_attention:
            continue
        if crit.exclude_day_trade_restricted and si.is_day_trade_restricted:
            continue
        if (crit.max_prior_limit_up_streak is not None
                and si.prior_limit_up_streak is not None
                and si.prior_limit_up_streak > crit.max_prior_limit_up_streak):
            continue
        out.append(si)
    # 依昨日量由大到小排序，截斷上限
    out.sort(key=lambda x: x.prev_volume, reverse=True)
    return out[: crit.max_candidates]


def resolve_preview_price(info: SymbolInfo) -> Decimal:
    """儀錶板預覽用價格：盤中取最新可用報價，收盤後通常會落在當日收盤價。"""
    if info.quote_price is not None and info.quote_price > 0:
        return info.quote_price
    return info.prev_close


def scan_preview_candidates(
    infos: Iterable[SymbolInfo],
    criteria: Optional[ScanCriteria] = None,
) -> List[SymbolInfo]:
    """儀錶板預覽用篩選：價格區間以可用報價判斷，不改動策略 scan_daily 的漲停價邏輯。"""
    crit = criteria or ScanCriteria()
    markets = set(crit.markets)
    out: List[SymbolInfo] = []
    for si in infos:
        if si.market not in markets:
            continue
        price = resolve_preview_price(si)
        if price <= 0:
            continue
        if not (crit.price_min <= price <= crit.price_max):
            continue
        if si.prev_volume < crit.min_prev_volume:
            continue
        if crit.exclude_disposal and si.is_disposal:
            continue
        if crit.exclude_attention and si.is_attention:
            continue
        if crit.exclude_day_trade_restricted and si.is_day_trade_restricted:
            continue
        if (crit.max_prior_limit_up_streak is not None
                and si.prior_limit_up_streak is not None
                and si.prior_limit_up_streak > crit.max_prior_limit_up_streak):
            continue
        out.append(si)
    out.sort(key=lambda x: x.prev_volume, reverse=True)
    return out[: crit.max_candidates]
