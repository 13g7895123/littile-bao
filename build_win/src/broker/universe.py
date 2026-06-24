"""
broker.universe — 個股基本資料 / 開盤前選股

Milestone 3：提供 SymbolInfo 載入（昨收 / 漲停價 / 特殊股標記）
Milestone 6：scan_daily() 全市場掃描（待實作）
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
    display_prev_close: Optional[Decimal] = None  # UI 漲跌比較基準；不影響策略昨收
    closed_at_limit_up: Optional[bool] = None


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


def next_session_prior_limit_up_streak(info: "SymbolInfo") -> Optional[int]:
    """用今日收盤快照推估隔日開盤前的連續收漲停天數。"""
    if info.quote_price is None or info.quote_price <= 0:
        return None
    if not is_limit_up_close(info.quote_price, info.prev_close):
        return 0
    return (info.prior_limit_up_streak or 0) + 1


def build_next_session_symbol_info(info: "SymbolInfo") -> Optional["SymbolInfo"]:
    """將收盤後快照轉成隔日選股會使用的 SymbolInfo。"""
    if info.quote_price is None or info.quote_price <= 0:
        return None
    return build_symbol_info(
        code=info.code,
        name=info.name,
        market=info.market,
        prev_close=info.quote_price,
        quote_price=info.quote_price,
        prev_volume=info.prev_volume,
        is_disposal=info.is_disposal,
        is_attention=info.is_attention,
        is_day_trade_restricted=info.is_day_trade_restricted,
        prior_limit_up_streak=next_session_prior_limit_up_streak(info),
    )


def _default_snapshot_cache_path() -> str:
    if getattr(__import__("sys"), "frozen", False):
        base = os.path.dirname(__import__("sys").executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "cache", "market_snapshots.json")


def _default_previous_trading_days_cache_path() -> str:
    if getattr(__import__("sys"), "frozen", False):
        base = os.path.dirname(__import__("sys").executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "cache", "previous_trading_days.json")


_TAIPEI_TZ = timezone(timedelta(hours=8))
PREVIOUS_TRADING_DAYS_API_URL = "https://stock.try-8verything.com/api/prices/previous-trading-days"


def _today_taipei_iso() -> str:
    return datetime.now(_TAIPEI_TZ).date().isoformat()


def _normalize_market(raw: object, *, fallback: str = "TSE") -> str:
    text = str(raw or fallback or "TSE").strip()
    upper = text.upper()
    lower = text.lower()
    if "OTC" in upper or "TPEX" in upper or "tpex" in lower:
        return "OTC"
    return "TSE"


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


class PreviousTradingDaysCache:
    """全市場前兩個交易日價量 API 的每日查詢快取。"""

    def __init__(self, path: str = "") -> None:
        self.path = path or _default_previous_trading_days_cache_path()
        self._queries: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            queries = raw.get("queries", {}) if isinstance(raw, dict) else {}
            if isinstance(queries, dict):
                self._queries = {
                    str(as_of): entry
                    for as_of, entry in queries.items()
                    if isinstance(entry, dict)
                }
        except Exception:
            self._queries = {}

    def get_payload(self, as_of: str) -> Optional[dict]:
        day = MarketSnapshotCache._normalize_date(as_of)
        if not day:
            return None
        entry = self._queries.get(day)
        if not isinstance(entry, dict):
            return None
        if entry.get("queried_on") != _today_taipei_iso():
            return None
        payload = entry.get("payload")
        return payload if isinstance(payload, dict) else None

    def store_payload(self, as_of: str, payload: dict, *, keep_days: int = 20) -> None:
        day = MarketSnapshotCache._normalize_date(as_of)
        if not day or not isinstance(payload, dict):
            return
        self._queries[day] = {
            "queried_on": _today_taipei_iso(),
            "fetched_at": datetime.now(_TAIPEI_TZ).isoformat(timespec="seconds"),
            "payload": payload,
        }
        self.save(keep_days=keep_days)

    def save(self, *, keep_days: int = 20) -> None:
        dates = sorted(self._queries.keys())
        if keep_days > 0 and len(dates) > keep_days:
            keep = set(dates[-keep_days:])
            self._queries = {
                day: entry for day, entry in self._queries.items()
                if day in keep
            }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {"version": 1, "queries": self._queries}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)


class PreviousTradingDaysApiClient:
    """呼叫全市場前兩個交易日價量 API，並轉為 SymbolInfo。"""

    def __init__(
        self,
        base_url: str = "",
        *,
        cache: Optional[PreviousTradingDaysCache] = None,
        timeout_sec: float = 10.0,
    ) -> None:
        self.base_url = (base_url or PREVIOUS_TRADING_DAYS_API_URL).strip()
        self.timeout_sec = timeout_sec
        self.cache = cache or PreviousTradingDaysCache()
        self.last_from_cache = False
        self.last_as_of = ""
        self.last_count = 0

    def load_symbol_infos(
        self,
        markets: Iterable[str] = ("TSE", "OTC"),
        *,
        as_of: str = "",
    ) -> Dict[str, SymbolInfo]:
        query_day = MarketSnapshotCache._normalize_date(as_of) or _today_taipei_iso()
        self.last_as_of = query_day
        self.last_from_cache = False

        payload = self.cache.get_payload(query_day)
        if payload is not None:
            self.last_from_cache = True
        else:
            payload = self._fetch_json(self._build_url(query_day))
            self.cache.store_payload(query_day, payload)

        infos = self.parse_payload(payload, markets=markets)
        self.last_count = len(infos)
        return infos

    def _build_url(self, as_of: str) -> str:
        params = urllib.parse.urlencode({"as_of": as_of})
        separator = "&" if "?" in self.base_url else "?"
        return f"{self.base_url}{separator}{params}"

    @staticmethod
    def _request_headers() -> dict:
        return {
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
        }

    def _fetch_json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers=self._request_headers())
        with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("previous trading days API response must be an object")
        if payload.get("error"):
            raise ValueError(str(payload.get("error")))
        return payload

    @classmethod
    def parse_payload(
        cls,
        payload: dict,
        *,
        markets: Iterable[str] = ("TSE", "OTC"),
    ) -> Dict[str, SymbolInfo]:
        allowed_markets = {_normalize_market(m) for m in (list(markets) or ["TSE", "OTC"])}
        items = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return {}

        out: Dict[str, SymbolInfo] = {}
        for item in items:
            info = cls._parse_symbol_item(item, allowed_markets)
            if info is not None:
                out[info.code] = info
        return out

    @classmethod
    def _parse_symbol_item(
        cls,
        item: object,
        allowed_markets: set,
    ) -> Optional[SymbolInfo]:
        if not isinstance(item, dict):
            return None

        code = str(item.get("symbol") or item.get("code") or "").strip()
        if not code:
            return None

        market = _normalize_market(item.get("market"), fallback="TSE")
        if market not in allowed_markets:
            return None

        rows = cls._parse_price_rows(item.get("data"))
        if not rows:
            return None

        latest = rows[0]
        prior = rows[1] if len(rows) > 1 else None
        prior_streak: Optional[int] = None
        if prior is not None:
            prior_streak = 1 if is_limit_up_close(latest[1], prior[1]) else 0

        return build_symbol_info(
            code=code,
            name=str(item.get("name") or code),
            market=market,
            prev_close=latest[1],
            quote_price=latest[1],
            prev_volume=latest[2],
            is_disposal=cls._bool_flag(
                item,
                "is_disposition", "is_disposal", "isDisposition", "isDisposal",
            ),
            is_attention=cls._bool_flag(
                item,
                "is_attention", "isAttention", "attention",
            ),
            is_day_trade_restricted=cls._bool_flag(
                item,
                "is_day_trade_restricted", "isDayTradeRestricted",
                "dayTradeRestricted",
            ),
            prior_limit_up_streak=prior_streak,
            display_prev_close=prior[1] if prior is not None else None,
            closed_at_limit_up=(prior_streak == 1) if prior is not None else None,
        )

    @classmethod
    def _parse_price_rows(cls, raw_rows: object) -> List[tuple[str, Decimal, int]]:
        if not isinstance(raw_rows, list):
            return []
        rows: List[tuple[str, Decimal, int]] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            day = MarketSnapshotCache._normalize_date(
                row.get("date") or row.get("tradeDate"))
            close_price = cls._decimal_value(row.get("close") or row.get("closePrice"))
            if not day or close_price is None:
                continue
            rows.append((day, close_price, cls._int_value(row.get("volume"))))
        rows.sort(key=lambda record: record[0], reverse=True)
        return rows

    @staticmethod
    def _decimal_value(raw: object) -> Optional[Decimal]:
        if raw in (None, "", "-"):
            return None
        try:
            value = Decimal(str(raw))
        except Exception:
            return None
        return value if value > 0 else None

    @staticmethod
    def _int_value(raw: object) -> int:
        if raw in (None, "", "-"):
            return 0
        try:
            return int(Decimal(str(raw)))
        except Exception:
            return 0

    @staticmethod
    def _bool_flag(item: dict, *names: str) -> bool:
        for name in names:
            value = item.get(name)
            if value is None:
                continue
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float, Decimal)):
                return bool(value)
            text = str(value).strip().lower()
            if text in ("1", "true", "t", "yes", "y", "是", "有"):
                return True
            if text in ("0", "false", "f", "no", "n", "否", "無", ""):
                return False
        return False


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
    display_prev_close: Optional[Decimal] = None,
    closed_at_limit_up: Optional[bool] = None,
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
        display_prev_close=display_prev_close,
        closed_at_limit_up=closed_at_limit_up,
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

        is_disposal = self._truthy_flag(
            g,
            "isDisposition", "isDispositionStock", "isDisposal",
            "is_disposition", "is_disposal", "disposition", "disposal",
        )
        is_attention = self._truthy_flag(
            g,
            "isAttention", "isAttentionStock", "is_attention", "attention",
        )
        is_day_trade_restricted = self._day_trade_restricted_flag(g)

        return build_symbol_info(
            code=code,
            name=str(g("name") or g("stock_name") or code),
            market=market,
            prev_close=pc,
            quote_price=quote_price,
            prev_volume=prev_vol,
            is_disposal=is_disposal,
            is_attention=is_attention,
            is_day_trade_restricted=is_day_trade_restricted,
        )

    @classmethod
    def _truthy_flag(cls, getter, *names: str) -> bool:
        for name in names:
            parsed = cls._parse_flag(getter(name, None))
            if parsed is True:
                return True
        return False

    @classmethod
    def _day_trade_restricted_flag(cls, getter) -> bool:
        if cls._truthy_flag(
            getter,
            "isDayTradeRestricted", "isDayTradingRestricted",
            "is_day_trade_restricted", "dayTradeRestricted",
            "day_trade_restricted", "dayTradeLimit", "day_trade_limit",
            "isDayTradeLimit", "isDayTradeSuspended",
        ):
            return True

        for name in (
            "canDayTrade", "can_day_trade", "dayTradeable", "day_tradeable",
            "isDayTrade", "is_day_trade", "dayTrade", "day_trade",
        ):
            parsed = cls._parse_flag(getter(name, None))
            if parsed is False:
                return True
        return False

    @staticmethod
    def _parse_flag(value) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float, Decimal)):
            return bool(value)
        text = str(value).strip().lower()
        if text in ("", "-", "none", "null"):
            return None
        if text in (
            "1", "true", "t", "y", "yes", "是", "有", "處置", "注意",
            "restricted", "suspended", "limit", "limited", "禁止", "禁當沖",
            "限當沖",
        ):
            return True
        if text in (
            "0", "false", "f", "n", "no", "否", "無", "normal", "allowed",
            "可", "可當沖",
        ):
            return False
        return None

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
    """從 infos（通常為全市場 SymbolInfo）篩出符合條件的候選清單。

    價格區間以「昨收 ± 10%」放寬判斷，涵蓋所有「即時價有機會落在 [price_min, price_max]」的標的；
    實際的即時價過濾由 engine.get_summary() / GUI 顯示層用 last_price 動態執行。
    """
    crit = criteria or ScanCriteria()
    markets = set(crit.markets)
    # 區間放寬係數：股票單日最多漲跌停 ±10%，所以昨收 *0.9 ~ *1.1 即可涵蓋所有可能進區間的標的
    EXPAND = Decimal("0.1")
    relaxed_min = crit.price_min * (Decimal("1") - EXPAND)
    relaxed_max = crit.price_max * (Decimal("1") + EXPAND)
    out: List[SymbolInfo] = []
    for si in infos:
        if si.market not in markets:
            continue
        # 用昨收（prev_close）判斷，而非漲停價
        ref_price = si.prev_close if si.prev_close and si.prev_close > 0 else si.limit_up_price
        if not (relaxed_min <= ref_price <= relaxed_max):
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
