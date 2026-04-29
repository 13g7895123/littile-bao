"""
broker.universe — 個股基本資料 / 開盤前選股

Milestone 3：提供 SymbolInfo 載入（昨收 / 漲停價 / 特殊股標記）
Milestone 6：scan_daily() 全市場掃描（待實作）
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Optional


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
    limit_up_price: Decimal
    limit_down_price: Decimal
    prev_volume: int = 0
    is_disposal: bool = False
    is_attention: bool = False
    is_day_trade_restricted: bool = False
    open_limit_up: bool = False  # 開盤後首筆 tick 才能確認，預設 False


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


# ─────────────────────────────────────────────────────────
#  載入器
# ─────────────────────────────────────────────────────────

def build_symbol_info(
    code: str,
    name: str,
    market: str,
    prev_close: float | Decimal,
    *,
    prev_volume: int = 0,
    is_disposal: bool = False,
    is_attention: bool = False,
    is_day_trade_restricted: bool = False,
) -> SymbolInfo:
    """以昨收價自動算出漲跌停。"""
    pc = Decimal(str(prev_close))
    return SymbolInfo(
        code=code,
        name=name,
        market=market,
        prev_close=pc,
        limit_up_price=calc_limit_up(pc),
        limit_down_price=calc_limit_down(pc),
        prev_volume=prev_volume,
        is_disposal=is_disposal,
        is_attention=is_attention,
        is_day_trade_restricted=is_day_trade_restricted,
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
    透過 fubon_neo SDK 取得個股基本資料（骨架）。

    SDK 路徑（不同版本可能略異）：
      sdk.marketdata.rest_client.stock.intraday.ticker(symbol)
      → 含 prevClose / referencePrice / isDisposition 等欄位

    特殊股 / 限當沖屬性需另呼叫對應 endpoint，本期僅提供骨架。
    """

    def __init__(self, adapter) -> None:
        self._adapter = adapter

    def load(self, codes: Iterable[str]) -> Dict[str, SymbolInfo]:
        try:
            sdk = self._adapter.sdk
        except Exception:  # noqa: BLE001
            return {}

        out: Dict[str, SymbolInfo] = {}
        rest = self._resolve_rest_stock(sdk)
        if rest is None:
            return {}
        for code in codes:
            try:
                raw = self._fetch_ticker(rest, code)
                if not raw:
                    continue
                pc = Decimal(str(
                    raw.get("previousClose")
                    or raw.get("prevClose")
                    or raw.get("referencePrice")
                    or 0
                ))
                if pc <= 0:
                    continue
                out[code] = build_symbol_info(
                    code=code,
                    name=str(raw.get("name") or code),
                    market=str(raw.get("market") or "TSE"),
                    prev_close=pc,
                    prev_volume=int(raw.get("totalVolume") or 0),
                    is_disposal=bool(raw.get("isDisposition") or raw.get("isDisposal")),
                    is_attention=bool(raw.get("isAttention")),
                    is_day_trade_restricted=bool(raw.get("isDayTradeRestricted")),
                )
            except Exception as e:  # noqa: BLE001
                print(f"[Universe] 載入 {code} 失敗：{e}")
        return out

    @staticmethod
    def _resolve_rest_stock(sdk):
        md = getattr(sdk, "marketdata", None)
        rc = getattr(md, "rest_client", None) if md else None
        return getattr(rc, "stock", None) if rc else None

    @staticmethod
    def _fetch_ticker(rest, code: str) -> Optional[dict]:
        intraday = getattr(rest, "intraday", None)
        if intraday is None:
            return None
        ticker = getattr(intraday, "ticker", None)
        if not callable(ticker):
            return None
        res = ticker(symbol=code) if "symbol" in ticker.__code__.co_varnames else ticker(code)
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
        out.append(si)
    # 依昨日量由大到小排序，截斷上限
    out.sort(key=lambda x: x.prev_volume, reverse=True)
    return out[: crit.max_candidates]
