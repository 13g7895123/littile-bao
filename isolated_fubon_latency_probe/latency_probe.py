#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence

from fubon_neo.adapter import Mode, build_websocket_client
from fubon_neo.sdk import FubonSDK


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "output"
DEFAULT_CONFIG_PATH = r"C:\Users\user\Downloads\trading_config_20260602_093245.json"
PREVIOUS_TRADING_DAYS_API_URL = "https://stock.try-8verything.com/api/prices/previous-trading-days"
CHANNELS = ("trades", "books")
MAX_CONNECTIONS = 5
MAX_SUBSCRIPTIONS_PER_CONNECTION = 200
SYMBOLS_PER_CONNECTION = MAX_SUBSCRIPTIONS_PER_CONNECTION // len(CHANNELS)
MAX_SYMBOLS = SYMBOLS_PER_CONNECTION * MAX_CONNECTIONS
CONTROL_EVENTS = {
    "authenticated",
    "heartbeat",
    "pong",
    "subscribed",
    "unsubscribed",
    "ticker",
    "error",
    "info",
}


@dataclass
class SymbolInfo:
    code: str
    name: str
    market: str
    prev_close: Decimal
    prev_volume: int
    prior_limit_up_streak: Optional[int]


def load_dotenv_if_exists() -> None:
    for candidate in (PROJECT_DIR / ".env", Path.cwd() / ".env", PROJECT_DIR.parent / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return


def normalize_windows_path(raw: str) -> str:
    value = raw.strip().strip('"').strip("'")
    if not value:
        return value
    if os.path.exists(value):
        return value
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", value)
    if match:
        drive = match.group(1).lower()
        tail = match.group(2).replace("\\", "/")
        converted = f"/mnt/{drive}/{tail}"
        if os.path.exists(converted):
            return converted
        return converted
    return value


def prompt_text(label: str, default: str = "", *, secret: bool = False, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        if secret:
            value = getpass.getpass(f"{label}{suffix}: ").strip()
        else:
            value = input(f"{label}{suffix}: ").strip()
        if not value:
            value = default.strip()
        if value or not required:
            return value
        print(f"{label} 不能空白")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError("trading config root must be an object")
    return data


def today_iso() -> str:
    return date.today().isoformat()


def decimal_value(raw: object) -> Optional[Decimal]:
    if raw in (None, "", "-"):
        return None
    try:
        value = Decimal(str(raw))
    except Exception:
        return None
    return value if value > 0 else None


def int_value(raw: object) -> int:
    if raw in (None, "", "-"):
        return 0
    try:
        return int(Decimal(str(raw)))
    except Exception:
        return 0


def tick_size(price: Decimal) -> Decimal:
    table = [
        (Decimal("10"), Decimal("0.01")),
        (Decimal("50"), Decimal("0.05")),
        (Decimal("100"), Decimal("0.1")),
        (Decimal("500"), Decimal("0.5")),
        (Decimal("1000"), Decimal("1")),
        (Decimal("9999999"), Decimal("5")),
    ]
    for upper, tick in table:
        if price < upper:
            return tick
    return Decimal("5")


def calc_limit_up(prev_close: Decimal) -> Decimal:
    raw = prev_close * Decimal("1.1")
    tick = tick_size(raw)
    return (raw // tick) * tick


def is_limit_up_close(close: Decimal, prev_close: Decimal) -> bool:
    return close == calc_limit_up(prev_close)


def normalize_market(raw: object) -> str:
    text = str(raw or "TSE").strip().upper()
    if "OTC" in text or "TPEX" in text:
        return "OTC"
    return "TSE"


def fetch_previous_trading_days(as_of: str) -> dict:
    params = urllib.parse.urlencode({"as_of": as_of})
    url = f"{PREVIOUS_TRADING_DAYS_API_URL}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "isolated-fubon-latency-probe/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("previous trading days API response must be an object")
    return payload


def parse_symbols(payload: dict, markets: Iterable[str]) -> Dict[str, SymbolInfo]:
    allowed = {normalize_market(m) for m in markets}
    items = payload.get("data")
    if not isinstance(items, list):
        return {}
    out: Dict[str, SymbolInfo] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("symbol") or item.get("code") or "").strip()
        if not code:
            continue
        market = normalize_market(item.get("market"))
        if market not in allowed:
            continue
        rows = item.get("data")
        if not isinstance(rows, list):
            continue
        parsed_rows: List[tuple[str, Decimal, int]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            day = str(row.get("date") or row.get("tradeDate") or "").strip()
            close_price = decimal_value(row.get("close") or row.get("closePrice"))
            if not day or close_price is None:
                continue
            parsed_rows.append((day, close_price, int_value(row.get("volume"))))
        parsed_rows.sort(key=lambda value: value[0], reverse=True)
        if not parsed_rows:
            continue
        latest = parsed_rows[0]
        prior = parsed_rows[1] if len(parsed_rows) > 1 else None
        prior_streak = None
        if prior is not None:
            prior_streak = 1 if is_limit_up_close(latest[1], prior[1]) else 0
        out[code] = SymbolInfo(
            code=code,
            name=str(item.get("name") or code),
            market=market,
            prev_close=latest[1],
            prev_volume=latest[2],
            prior_limit_up_streak=prior_streak,
        )
    return out


def scan_candidates(config: dict, infos: Sequence[SymbolInfo]) -> List[SymbolInfo]:
    price_min = Decimal(str(config.get("price_min", 0))) if config.get("f9_enabled", True) else Decimal("0")
    price_max = Decimal(str(config.get("price_max", 999999))) if config.get("f9_enabled", True) else Decimal("999999")
    min_prev_volume = int(config.get("daily_volume_min", 0)) if config.get("f8_enabled", True) else 0
    markets: List[str] = []
    if config.get("market_twse", True):
        markets.append("TSE")
    if config.get("market_tpex", True):
        markets.append("OTC")
    allowed_markets = set(markets or ["TSE", "OTC"])
    max_prior_streak = None
    if config.get("f7_enabled", True) and int(config.get("candle_limit", 0) or 0) > 0:
        max_prior_streak = int(config["candle_limit"]) - 1

    expand = Decimal("0.1")
    relaxed_min = price_min * (Decimal("1") - expand)
    relaxed_max = price_max * (Decimal("1") + expand)

    selected: List[SymbolInfo] = []
    for info in infos:
        if info.market not in allowed_markets:
            continue
        ref_price = info.prev_close
        if ref_price <= 0:
            continue
        if not (relaxed_min <= ref_price <= relaxed_max):
            continue
        if info.prev_volume < min_prev_volume:
            continue
        if max_prior_streak is not None and info.prior_limit_up_streak is not None:
            if info.prior_limit_up_streak > max_prior_streak:
                continue
        selected.append(info)
    selected.sort(key=lambda item: item.prev_volume, reverse=True)
    return selected[:MAX_SYMBOLS]


def parse_api_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        raw = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            try:
                raw = float(text)
            except ValueError:
                return None
    abs_raw = abs(raw)
    if abs_raw >= 1_000_000_000_000_000_000:
        seconds = raw / 1_000_000_000
    elif abs_raw >= 1_000_000_000_000_000:
        seconds = raw / 1_000_000
    elif abs_raw >= 1_000_000_000_000:
        seconds = raw / 1_000
    else:
        seconds = raw
    try:
        return datetime.fromtimestamp(seconds)
    except Exception:
        return None


def percentile(values: Sequence[float], ratio: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = (len(ordered) - 1) * ratio
    lo = int(index)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    weight = index - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


class LatencyCollector:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.events_path = self.output_dir / f"latency_events_{stamp}.jsonl"
        self.summary_path = self.output_dir / f"latency_summary_{stamp}.json"
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {
            "raw_messages": 0,
            "control_messages": 0,
            "trade_events": 0,
            "book_events": 0,
            "backfill_trade_events": 0,
            "backfill_book_events": 0,
            "live_trade_events": 0,
            "live_book_events": 0,
        }
        self._latencies: Dict[str, List[float]] = {"trades": [], "books": [], "all": []}
        self._live_latencies: Dict[str, List[float]] = {"trades": [], "books": [], "all": []}
        self._first_event_at: Dict[str, float] = {}
        self._first_valid_latency_at: Dict[str, float] = {}
        self._sample_events_written = 0

    def record_control(self) -> None:
        with self._lock:
            self._counts["control_messages"] += 1

    def record_raw(self) -> None:
        with self._lock:
            self._counts["raw_messages"] += 1

    def record_event(
        self,
        *,
        channel: str,
        code: str,
        api_time: Optional[datetime],
        recv_time: datetime,
        payload: dict,
        subscribe_wall_time: Optional[datetime],
        subscribe_sent_at: Optional[float],
    ) -> None:
        latency_ms = None
        if api_time is not None:
            latency_ms = (recv_time - api_time).total_seconds() * 1000.0
        is_backfill = bool(
            api_time is not None
            and subscribe_wall_time is not None
            and api_time < (subscribe_wall_time.replace(microsecond=0))
        )

        with self._lock:
            if channel == "trades":
                self._counts["trade_events"] += 1
                self._counts["backfill_trade_events" if is_backfill else "live_trade_events"] += 1
            elif channel == "books":
                self._counts["book_events"] += 1
                self._counts["backfill_book_events" if is_backfill else "live_book_events"] += 1

            if channel not in self._first_event_at and subscribe_sent_at is not None:
                self._first_event_at[channel] = (time.perf_counter() - subscribe_sent_at) * 1000.0

            if latency_ms is not None:
                self._latencies[channel].append(latency_ms)
                self._latencies["all"].append(latency_ms)
                if not is_backfill:
                    self._live_latencies[channel].append(latency_ms)
                    self._live_latencies["all"].append(latency_ms)
                if channel not in self._first_valid_latency_at and subscribe_sent_at is not None:
                    self._first_valid_latency_at[channel] = (time.perf_counter() - subscribe_sent_at) * 1000.0

            if self._sample_events_written < 300:
                event = {
                    "recv_time": recv_time.isoformat(timespec="microseconds"),
                    "api_time": api_time.isoformat(timespec="microseconds") if api_time else None,
                    "latency_ms": round(latency_ms, 3) if latency_ms is not None else None,
                    "channel": channel,
                    "code": code,
                    "is_backfill": is_backfill,
                    "payload": payload,
                }
                with self.events_path.open("a", encoding="utf-8") as fp:
                    fp.write(json.dumps(event, ensure_ascii=False) + "\n")
                self._sample_events_written += 1

    def summary(self, *, started_at: str, ended_at: str, duration_sec: int, config_path: str, selected_symbols: Sequence[str]) -> dict:
        with self._lock:
            result = {
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_sec": duration_sec,
                "config_path": config_path,
                "selected_symbol_count": len(selected_symbols),
                "selected_symbols": list(selected_symbols),
                "counts": dict(self._counts),
                "first_event_after_subscribe_ms": {k: round(v, 3) for k, v in self._first_event_at.items()},
                "first_valid_latency_after_subscribe_ms": {k: round(v, 3) for k, v in self._first_valid_latency_at.items()},
                "latency_ms": {},
                "live_latency_ms": {},
                "events_path": str(self.events_path),
            }
            for channel, values in self._latencies.items():
                result["latency_ms"][channel] = summarize_values(values)
            for channel, values in self._live_latencies.items():
                result["live_latency_ms"][channel] = summarize_values(values)
            self.summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            result["summary_path"] = str(self.summary_path)
            return result


def summarize_values(values: Sequence[float]) -> dict:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
        "avg": round(mean(ordered), 3),
        "median": round(median(ordered), 3),
        "p95": round(percentile(ordered, 0.95) or ordered[-1], 3),
        "p99": round(percentile(ordered, 0.99) or ordered[-1], 3),
    }


class StandaloneRealtimeProbe:
    def __init__(self, sdk: FubonSDK, collector: LatencyCollector) -> None:
        self.sdk = sdk
        self.collector = collector
        self.ws_clients: List[Any] = []
        self.subscribe_sent_at: Optional[float] = None
        self.subscribe_wall_time: Optional[datetime] = None
        self._disconnected = False

    def start(self, symbols: Sequence[str]) -> None:
        self.sdk.init_realtime(Mode.Normal)
        base_client = getattr(getattr(self.sdk, "marketdata", None), "websocket_client", None)
        stock_client = getattr(base_client, "stock", None) if base_client is not None else None
        if stock_client is None:
            raise RuntimeError("SDK did not expose marketdata.websocket_client.stock")

        token = str(self.sdk.exchange_realtime_token())
        symbol_chunks = [list(symbols[i:i + SYMBOLS_PER_CONNECTION]) for i in range(0, len(symbols), SYMBOLS_PER_CONNECTION)]
        if not symbol_chunks:
            raise RuntimeError("No symbols to subscribe")

        self.ws_clients = [stock_client]
        while len(self.ws_clients) < len(symbol_chunks):
            wrapper = build_websocket_client(Mode.Normal, token)
            self.ws_clients.append(wrapper.stock)

        for index, ws in enumerate(self.ws_clients[: len(symbol_chunks)]):
            self._register_handlers(ws, index)
            ws.connect()
        self.subscribe_wall_time = datetime.now()
        self.subscribe_sent_at = time.perf_counter()
        for index, chunk in enumerate(symbol_chunks):
            ws = self.ws_clients[index]
            for channel in CHANNELS:
                ws.subscribe({"channel": channel, "symbols": chunk})

    def stop(self) -> None:
        for ws in self.ws_clients:
            try:
                ws.disconnect()
            except Exception:
                pass

    def _register_handlers(self, ws: Any, index: int) -> None:
        ws.on("connect", lambda *args, _index=index, **kwargs: print(f"[ws#{_index + 1}] connected"))
        ws.on("disconnect", lambda *args, _index=index, **kwargs: self._on_disconnect(_index, args, kwargs))
        ws.on("error", lambda *args, _index=index, **kwargs: self._on_error(_index, args, kwargs))
        ws.on("message", self._on_message)

    def _on_disconnect(self, index: int, args: tuple, kwargs: dict) -> None:
        self._disconnected = True
        print(f"[ws#{index + 1}] disconnected args={args} kwargs={kwargs}")

    def _on_error(self, index: int, args: tuple, kwargs: dict) -> None:
        print(f"[ws#{index + 1}] error args={args} kwargs={kwargs}")

    def _on_message(self, msg: Any) -> None:
        self.collector.record_raw()
        payload = extract_payload(msg)
        if not payload:
            return

        raw_event = str(payload.get("event") or "").lower()
        raw_channel = str(payload.get("channel") or "").lower()
        if raw_event in CONTROL_EVENTS:
            self.collector.record_control()
            return

        event = raw_channel or raw_event
        data = payload.get("data")
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            items = [data]
        elif isinstance(payload, dict):
            items = [payload]
        else:
            items = []

        for item in items:
            channel = classify_channel(event, item)
            if channel not in CHANNELS:
                continue
            recv_time = datetime.now()
            api_time = parse_api_datetime(item.get("time") or item.get("timestamp") or item.get("matchTime") or item.get("tradeTime"))
            code = str(item.get("symbol") or item.get("code") or item.get("stockNo") or item.get("stock_no") or "").strip()
            self.collector.record_event(
                channel=channel,
                code=code,
                api_time=api_time,
                recv_time=recv_time,
                payload=item,
                subscribe_wall_time=self.subscribe_wall_time,
                subscribe_sent_at=self.subscribe_sent_at,
            )


def classify_channel(event: str, payload: dict) -> str:
    if event in CHANNELS:
        return event
    has_book_fields = any(key in payload for key in ("asks", "bids", "ask", "bid"))
    if has_book_fields:
        return "books"
    has_trade_fields = ("price" in payload or "lastPrice" in payload or "closePrice" in payload or "matchPrice" in payload) and (
        "size" in payload or "volume" in payload or "lastSize" in payload or "qty" in payload
    )
    if has_trade_fields:
        return "trades"
    return ""


def extract_payload(msg: Any) -> Optional[dict]:
    if msg is None:
        return None
    if isinstance(msg, dict):
        return msg
    if isinstance(msg, (bytes, bytearray)):
        try:
            msg = msg.decode("utf-8", errors="ignore")
        except Exception:
            return None
    if isinstance(msg, str):
        try:
            obj = json.loads(msg)
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None
    data_attr = getattr(msg, "data", None)
    if isinstance(data_attr, dict):
        return data_attr
    if isinstance(data_attr, str):
        try:
            obj = json.loads(data_attr)
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None
    return None


def login_sdk(
    *,
    personal_id: str,
    password: str,
    cert_path: str,
    cert_password: str,
    api_key: str,
) -> FubonSDK:
    sdk = FubonSDK()
    if api_key and cert_path:
        result = sdk.apikey_login(personal_id, api_key, cert_path, cert_password or personal_id)
    elif api_key:
        result = sdk.apikey_dma_login(personal_id, api_key)
    else:
        result = sdk.login(personal_id, password, cert_path, cert_password or personal_id)

    is_success = bool(getattr(result, "is_success", False) or getattr(result, "success", False))
    accounts = getattr(result, "data", None) or getattr(result, "accounts", None) or []
    if not is_success and not accounts:
        message = getattr(result, "message", None) or getattr(result, "msg", None) or str(result)
        raise RuntimeError(f"login failed: {message}")
    return sdk


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone Fubon realtime latency probe")
    parser.add_argument("--duration-sec", type=int, default=180, help="How long to subscribe before summarizing")
    parser.add_argument("--config-path", default="", help="Trading config path; interactive prompt when omitted")
    parser.add_argument("--non-interactive", action="store_true", help="Use environment variables without prompts")
    return parser


def main() -> int:
    load_dotenv_if_exists()
    parser = build_parser()
    args = parser.parse_args()

    env_config = os.environ.get("TRADING_CONFIG_PATH", "").strip() or DEFAULT_CONFIG_PATH
    config_input = args.config_path or env_config
    if args.non_interactive:
        config_path = normalize_windows_path(config_input)
        personal_id = os.environ.get("FUBON_PERSONAL_ID", "").strip()
        password = os.environ.get("FUBON_PASSWORD", "")
        cert_path = normalize_windows_path(os.environ.get("FUBON_CERT_PATH", "").strip())
        cert_password = os.environ.get("FUBON_CERT_PASSWORD", "")
        api_key = os.environ.get("FUBON_API_KEY", "").strip()
    else:
        print("=== Standalone Fubon Latency Probe ===")
        config_path = normalize_windows_path(prompt_text("設定檔路徑", config_input, required=True))
        personal_id = prompt_text("身分證字號", os.environ.get("FUBON_PERSONAL_ID", "").strip(), required=True)
        password = prompt_text("網路下單密碼", os.environ.get("FUBON_PASSWORD", ""), secret=True)
        cert_default = normalize_windows_path(os.environ.get("FUBON_CERT_PATH", "").strip())
        cert_path = normalize_windows_path(prompt_text("憑證路徑", cert_default, required=not bool(os.environ.get("FUBON_API_KEY", "").strip())))
        cert_password = prompt_text("憑證密碼", os.environ.get("FUBON_CERT_PASSWORD", ""), secret=True)
        api_key = prompt_text("API Key", os.environ.get("FUBON_API_KEY", "").strip())

    if not config_path or not os.path.exists(config_path):
        raise FileNotFoundError(f"config path not found: {config_path}")

    config = load_config(config_path)
    markets = []
    if config.get("market_twse", True):
        markets.append("TSE")
    if config.get("market_tpex", True):
        markets.append("OTC")
    payload = fetch_previous_trading_days(today_iso())
    infos = parse_symbols(payload, markets or ["TSE", "OTC"])
    candidates = scan_candidates(config, list(infos.values()))
    if not candidates:
        raise RuntimeError("No candidate symbols matched the trading config")

    symbols = [item.code for item in candidates]
    print(f"Config: {config_path}")
    print(f"Candidates selected: {len(symbols)}")
    print(f"First 20 symbols: {symbols[:20]}")
    print(f"Duration: {args.duration_sec} seconds")

    sdk = login_sdk(
        personal_id=personal_id,
        password=password,
        cert_path=cert_path,
        cert_password=cert_password,
        api_key=api_key,
    )
    collector = LatencyCollector(OUTPUT_DIR)
    probe = StandaloneRealtimeProbe(sdk, collector)
    started_at = datetime.now().isoformat(timespec="seconds")

    try:
        probe.start(symbols)
        deadline = time.time() + args.duration_sec
        while time.time() < deadline:
            remaining = max(0, int(round(deadline - time.time())))
            if remaining % 30 == 0:
                print(f"... remaining {remaining}s")
            time.sleep(1)
    finally:
        probe.stop()
        try:
            sdk.logout()
        except Exception:
            pass

    ended_at = datetime.now().isoformat(timespec="seconds")
    summary = collector.summary(
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=args.duration_sec,
        config_path=config_path,
        selected_symbols=symbols,
    )

    print_summary(summary)
    return 0


def print_summary(summary: dict) -> None:
    print("\n=== Summary ===")
    print(f"Summary file: {summary['summary_path']}")
    print(f"Sample events: {summary['events_path']}")
    print(f"Selected symbols: {summary['selected_symbol_count']}")
    counts = summary["counts"]
    print(
        "Counts: "
        f"raw={counts['raw_messages']} "
        f"control={counts['control_messages']} "
        f"trades={counts['trade_events']} "
        f"books={counts['book_events']}"
    )
    for channel in ("trades", "books", "all"):
        stats = summary["latency_ms"].get(channel) or {}
        if stats.get("count", 0) == 0:
            print(f"{channel}: no valid api_time samples")
            continue
        print(
            f"{channel}: count={stats['count']} avg={stats['avg']:.3f}ms "
            f"median={stats['median']:.3f}ms p95={stats['p95']:.3f}ms "
            f"p99={stats['p99']:.3f}ms min={stats['min']:.3f}ms max={stats['max']:.3f}ms"
        )
    for channel in ("trades", "books", "all"):
        stats = summary["live_latency_ms"].get(channel) or {}
        if stats.get("count", 0) == 0:
            print(f"live {channel}: no valid post-subscribe samples")
            continue
        print(
            f"live {channel}: count={stats['count']} avg={stats['avg']:.3f}ms "
            f"median={stats['median']:.3f}ms p95={stats['p95']:.3f}ms "
            f"p99={stats['p99']:.3f}ms min={stats['min']:.3f}ms max={stats['max']:.3f}ms"
        )
    if summary["first_event_after_subscribe_ms"]:
        print(f"First event after subscribe: {summary['first_event_after_subscribe_ms']}")
    if summary["first_valid_latency_after_subscribe_ms"]:
        print(f"First valid latency sample after subscribe: {summary['first_valid_latency_after_subscribe_ms']}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
