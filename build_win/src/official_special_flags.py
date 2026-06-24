from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional
from urllib.request import urlopen


JsonLoader = Callable[[str], object]


def roc_date_text(day: date) -> str:
    return f"{day.year - 1911:03d}{day.month:02d}{day.day:02d}"


def cache_path(base_dir: str, day: date) -> Path:
    return Path(base_dir) / "cache" / f"official_special_flags_{day:%Y%m%d}.json"


def load_cached_payload(
    base_dir: str,
    day: date,
    markets: Iterable[str],
) -> Optional[dict]:
    path = cache_path(base_dir, day)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if is_payload_fresh(payload, day, markets):
        return payload
    return None


def load_recent_cached_payload(
    base_dir: str,
    day: date,
    markets: Iterable[str],
    *,
    max_lookback_days: int = 7,
) -> Optional[dict]:
    for offset in range(1, max(1, int(max_lookback_days or 1)) + 1):
        candidate_day = day - timedelta(days=offset)
        payload = load_cached_payload(base_dir, candidate_day, markets)
        if payload is not None:
            return payload
    return None


def save_payload(base_dir: str, day: date, payload: dict) -> Path:
    path = cache_path(base_dir, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_today_payload(
    *,
    base_dir: str,
    markets: Iterable[str],
    now: Optional[datetime] = None,
    json_loader: Optional[JsonLoader] = None,
    allow_previous_cache: bool = False,
) -> tuple[Optional[dict], str]:
    current = now or datetime.now()
    day = current.date()
    payload = load_cached_payload(base_dir, day, markets)
    if payload is not None:
        return payload, "cache"

    payload = fetch_payload(markets=markets, now=current, json_loader=json_loader)
    if not is_payload_fresh(payload, day, markets):
        if allow_previous_cache:
            previous_payload = load_recent_cached_payload(base_dir, day, markets)
            if previous_payload is not None:
                return previous_payload, "previous_cache"
        return None, "stale"

    save_payload(base_dir, day, payload)
    return payload, "api"


def is_payload_fresh(payload: object, day: date, markets: Iterable[str]) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("generated_date") != day.isoformat():
        return False
    if payload.get("trade_date_roc") != roc_date_text(day):
        return False

    source_dates = payload.get("source_dates")
    if not isinstance(source_dates, dict):
        return False

    target_roc = roc_date_text(day)
    wanted = set(markets or [])
    required_sources = []
    if "TSE" in wanted:
        required_sources.append("twse_daytrade_daily")
    if "OTC" in wanted:
        required_sources.append("tpex_securities")

    for source in required_sources:
        dates = source_dates.get(source)
        if not isinstance(dates, list) or target_roc not in dates:
            return False
    return True


def fetch_payload(
    *,
    markets: Iterable[str],
    now: Optional[datetime] = None,
    json_loader: Optional[JsonLoader] = None,
) -> dict:
    current = now or datetime.now()
    load_json = json_loader or _load_json
    wanted = set(markets or [])
    flags: Dict[str, dict] = {}
    source_dates: Dict[str, list[str]] = {}

    if "TSE" in wanted:
        _consume_twse_notice(
            load_json("https://openapi.twse.com.tw/v1/announcement/notice"),
            flags,
            source_dates,
        )
        _consume_twse_punish(
            load_json("https://openapi.twse.com.tw/v1/announcement/punish"),
            flags,
            source_dates,
        )
        _consume_twse_daytrade_daily(
            load_json("https://openapi.twse.com.tw/v1/exchangeReport/TWTB4U"),
            flags,
            source_dates,
        )
        _consume_twse_daytrade_pre(
            load_json("https://openapi.twse.com.tw/v1/exchangeReport/TWTBAU1"),
            flags,
            source_dates,
        )

    if "OTC" in wanted:
        _consume_tpex_warning(
            load_json("https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information"),
            flags,
            source_dates,
        )
        _consume_tpex_disposal(
            load_json("https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"),
            flags,
            source_dates,
        )
        _consume_tpex_securities(
            load_json("https://www.tpex.org.tw/openapi/v1/tpex_securities"),
            flags,
            source_dates,
        )
        _consume_tpex_daytrade_pre(
            load_json("https://www.tpex.org.tw/openapi/v1/tpex_intraday_trading_pre"),
            flags,
            source_dates,
        )

    return {
        "version": 1,
        "generated_at": current.isoformat(timespec="seconds"),
        "generated_date": current.date().isoformat(),
        "trade_date_roc": roc_date_text(current.date()),
        "markets": sorted(wanted),
        "source_dates": source_dates,
        "flags": flags,
    }


def _load_json(url: str) -> object:
    with urlopen(url, timeout=20) as response:
        raw = response.read().decode("utf-8-sig", errors="replace")
    return json.loads(raw)


def _mark(
    flags: Dict[str, dict],
    *,
    code: str,
    name: str = "",
    market: str = "",
    is_attention: bool = False,
    is_disposal: bool = False,
    is_day_trade_restricted: bool = False,
) -> None:
    code_text = str(code or "").strip()
    if not code_text:
        return
    row = flags.setdefault(code_text, {
        "name": "",
        "market": "",
        "is_attention": False,
        "is_disposal": False,
        "is_day_trade_restricted": False,
    })
    if name and not row["name"]:
        row["name"] = str(name).strip()
    if market and not row["market"]:
        row["market"] = market
    row["is_attention"] = row["is_attention"] or bool(is_attention)
    row["is_disposal"] = row["is_disposal"] or bool(is_disposal)
    row["is_day_trade_restricted"] = (
        row["is_day_trade_restricted"] or bool(is_day_trade_restricted)
    )


def _record_date(source_dates: Dict[str, list[str]], source: str, value: object) -> None:
    text = str(value or "").strip()
    if not text:
        return
    rows = source_dates.setdefault(source, [])
    if text not in rows:
        rows.append(text)


def _consume_twse_notice(payload: object, flags: Dict[str, dict], source_dates: Dict[str, list[str]]) -> None:
    if not isinstance(payload, list):
        return
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get("Code") or "").strip()
        if not code:
            continue
        _mark(flags, code=code, name=str(row.get("Name") or ""), market="TSE", is_attention=True)
        _record_date(source_dates, "twse_notice", row.get("Date"))


def _consume_twse_punish(payload: object, flags: Dict[str, dict], source_dates: Dict[str, list[str]]) -> None:
    if not isinstance(payload, list):
        return
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get("Code") or "").strip()
        if not code:
            continue
        _mark(flags, code=code, name=str(row.get("Name") or ""), market="TSE", is_disposal=True)
        _record_date(source_dates, "twse_punish", row.get("Date"))


def _consume_twse_daytrade_daily(payload: object, flags: Dict[str, dict], source_dates: Dict[str, list[str]]) -> None:
    if not isinstance(payload, list):
        return
    for row in payload:
        if not isinstance(row, dict):
            continue
        _record_date(source_dates, "twse_daytrade_daily", row.get("Date"))
        if str(row.get("Suspension") or "").strip():
            _mark(
                flags,
                code=str(row.get("Code") or ""),
                name=str(row.get("Name") or ""),
                market="TSE",
                is_day_trade_restricted=True,
            )


def _consume_twse_daytrade_pre(payload: object, flags: Dict[str, dict], source_dates: Dict[str, list[str]]) -> None:
    if not isinstance(payload, list):
        return
    for row in payload:
        if not isinstance(row, dict):
            continue
        _record_date(source_dates, "twse_daytrade_pre", row.get("StartDate"))
        _mark(
            flags,
            code=str(row.get("Code") or ""),
            name=str(row.get("Name") or ""),
            market="TSE",
            is_day_trade_restricted=True,
        )


def _consume_tpex_warning(payload: object, flags: Dict[str, dict], source_dates: Dict[str, list[str]]) -> None:
    if not isinstance(payload, list):
        return
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get("SecuritiesCompanyCode") or "").strip()
        if not code:
            continue
        _mark(flags, code=code, name=str(row.get("CompanyName") or ""), market="OTC", is_attention=True)
        _record_date(source_dates, "tpex_warning", row.get("Date"))


def _consume_tpex_disposal(payload: object, flags: Dict[str, dict], source_dates: Dict[str, list[str]]) -> None:
    if not isinstance(payload, list):
        return
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get("SecuritiesCompanyCode") or "").strip()
        if not code:
            continue
        _mark(flags, code=code, name=str(row.get("CompanyName") or ""), market="OTC", is_disposal=True)
        _record_date(source_dates, "tpex_disposal", row.get("Date"))


def _consume_tpex_securities(payload: object, flags: Dict[str, dict], source_dates: Dict[str, list[str]]) -> None:
    if not isinstance(payload, list):
        return
    for row in payload:
        if not isinstance(row, dict):
            continue
        _record_date(source_dates, "tpex_securities", row.get("資料日期"))
        if str(row.get("暫停現股賣出後現款買進當沖註記") or "").strip():
            _mark(
                flags,
                code=str(row.get("證券代號") or ""),
                name=str(row.get("證券名稱") or ""),
                market="OTC",
                is_day_trade_restricted=True,
            )


def _consume_tpex_daytrade_pre(payload: object, flags: Dict[str, dict], source_dates: Dict[str, list[str]]) -> None:
    if not isinstance(payload, list):
        return
    for row in payload:
        if not isinstance(row, dict):
            continue
        _record_date(source_dates, "tpex_daytrade_pre", row.get("Date"))
        _mark(
            flags,
            code=str(row.get("SecuritiesCompanyCode") or ""),
            name=str(row.get("CompanyName") or ""),
            market="OTC",
            is_day_trade_restricted=True,
        )
