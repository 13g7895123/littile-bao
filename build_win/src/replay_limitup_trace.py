"""
回放錄盤 tick/book，重建單一鎖板模式的狀態切換時間軸。

用法：
    python3 replay_limitup_trace.py <session_ticks.ndjson.gz> --code 4939
    python3 replay_limitup_trace.py <session_ticks.ndjson.gz> --code 5202 --code 6432 --mode bid_or_trade_flag
"""
from __future__ import annotations

import argparse
import json
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from limitup_detection import evaluate_limit_up_state, resolve_limit_up_mode


@dataclass
class ReplayState:
    code: str
    limit_up: Decimal
    last_price: Optional[Decimal] = None
    trade_bid: Optional[Decimal] = None
    trade_ask: Optional[Decimal] = None
    trade_is_limit_up_price: Optional[bool] = None
    trade_is_limit_up_bid: Optional[bool] = None
    trade_is_limit_up_ask: Optional[bool] = None
    ask0_price: Optional[Decimal] = None
    ask0_volume: int = 0
    bid0_price: Optional[Decimal] = None
    bid0_volume: int = 0
    has_ask_levels: bool = False
    has_bid_levels: bool = False
    current_locked: bool = False
    transitions: List[dict] = field(default_factory=list)


def _to_decimal(value) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _delay_ms(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() * 1000, 3)


def _load_meta_map(ticks_path: Path) -> Dict[str, Decimal]:
    meta_name = ticks_path.name.replace(".ticks.ndjson.gz", ".meta.json").replace(".ticks.ndjson", ".meta.json")
    meta_path = ticks_path.with_name(meta_name)
    if not meta_path.exists():
        raise FileNotFoundError(f"找不到對應 meta.json：{meta_path}")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    result: Dict[str, Decimal] = {}
    for item in meta.get("symbol_universe", []) or []:
        code = str(item.get("code") or "").strip()
        limit_up = item.get("limit_up")
        if code and limit_up not in (None, ""):
            result[code] = Decimal(str(limit_up))
    return result


def _iter_rows(path: Path) -> Iterable[dict]:
    if path.suffix != ".gz":
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
        return

    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    pending = ""
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            try:
                text = decoder.decompress(chunk).decode("utf-8", errors="ignore")
            except zlib.error:
                text = ""
            if not text:
                continue
            pending += text
            lines = pending.splitlines(keepends=False)
            if pending and not pending.endswith(("\n", "\r")):
                pending = lines.pop() if lines else pending
            else:
                pending = ""
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
    if pending.strip():
        try:
            row = json.loads(pending.strip())
        except json.JSONDecodeError:
            row = None
        if isinstance(row, dict):
            yield row


def _apply_row(state: ReplayState, row: dict) -> None:
    if row.get("kind") == "tick":
        state.last_price = _to_decimal(row.get("price"))
        state.trade_bid = _to_decimal(row.get("bid"))
        state.trade_ask = _to_decimal(row.get("ask"))
        state.trade_is_limit_up_price = row.get("is_limit_up_price")
        state.trade_is_limit_up_bid = row.get("is_limit_up_bid")
        state.trade_is_limit_up_ask = row.get("is_limit_up_ask")
        return
    if row.get("kind") == "book":
        asks = row.get("ask") or []
        bids = row.get("bid") or []
        state.has_ask_levels = bool(asks)
        state.has_bid_levels = bool(bids)
        if asks:
            state.ask0_price = _to_decimal(asks[0].get("price"))
            state.ask0_volume = int(asks[0].get("volume") or 0)
        else:
            state.ask0_price = None
            state.ask0_volume = 0
        if bids:
            state.bid0_price = _to_decimal(bids[0].get("price"))
            state.bid0_volume = int(bids[0].get("volume") or 0)
        else:
            state.bid0_price = None
            state.bid0_volume = 0


def replay(path: Path, codes: List[str], mode: str, limit_up_overrides: Optional[Dict[str, Decimal]] = None) -> Dict[str, ReplayState]:
    limit_map = _load_meta_map(path)
    if limit_up_overrides:
        limit_map.update(limit_up_overrides)
    code_set = {code.strip() for code in codes if code.strip()}
    states: Dict[str, ReplayState] = {}
    for row in _iter_rows(path):
        code = str(row.get("code") or "").strip()
        if not code or row.get("kind") not in {"tick", "book"}:
            continue
        if code_set and code not in code_set:
            continue
        limit_up = limit_map.get(code)
        if limit_up is None:
            continue
        state = states.setdefault(code, ReplayState(code=code, limit_up=limit_up))
        _apply_row(state, row)
        decision = evaluate_limit_up_state(
            limit_up=state.limit_up,
            ask0_price=state.ask0_price,
            ask0_volume=state.ask0_volume,
            bid0_price=state.bid0_price,
            bid0_volume=state.bid0_volume,
            last_price=state.last_price,
            trade_bid=state.trade_bid,
            trade_ask=state.trade_ask,
            has_ask_levels=state.has_ask_levels,
            has_bid_levels=state.has_bid_levels,
            is_limit_up_price=state.trade_is_limit_up_price,
            is_limit_up_bid=state.trade_is_limit_up_bid,
            is_limit_up_ask=state.trade_is_limit_up_ask,
        )
        locked = bool(decision["candidates"].get(mode, False))
        if locked == state.current_locked:
            continue
        event_time = _parse_dt(row.get("api_time") or row.get("time"))
        recv_time = _parse_dt(row.get("recv_time"))
        state.transitions.append({
            "kind": row.get("kind"),
            "locked": locked,
            "event_time": event_time.isoformat() if event_time else None,
            "recv_time": recv_time.isoformat() if recv_time else None,
            "market_to_recv_ms": _delay_ms(event_time, recv_time),
            "last_price": str(state.last_price) if state.last_price is not None else None,
            "ask0_price": str(state.ask0_price) if state.ask0_price is not None else None,
            "ask0_volume": state.ask0_volume,
            "bid0_price": str(state.bid0_price) if state.bid0_price is not None else None,
            "bid0_volume": state.bid0_volume,
            "signals": dict(decision["signals"]),
            "candidates": dict(decision["candidates"]),
        })
        state.current_locked = locked
    return states


def _print_report(states: Dict[str, ReplayState], mode: str, max_events: int) -> None:
    if not states:
        print("沒有符合條件的錄盤資料。")
        return
    for code in sorted(states):
        state = states[code]
        print(f"=== {code} mode={mode} limit_up={state.limit_up} transitions={len(state.transitions)} ===")
        for item in state.transitions[:max_events]:
            direction = "LOCK" if item["locked"] else "UNLOCK"
            print(
                f"{direction} kind={item['kind']} "
                f"event={item['event_time']} recv={item['recv_time']} "
                f"delay_ms={item['market_to_recv_ms']} "
                f"last={item['last_price']} ask0={item['ask0_price']}/{item['ask0_volume']} "
                f"bid0={item['bid0_price']}/{item['bid0_volume']}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="回放錄盤檔中的鎖板狀態切換")
    parser.add_argument("path", help="session_*.ticks.ndjson.gz 或 .ndjson")
    parser.add_argument("--code", action="append", default=[], help="只分析指定股票，可重複帶多次")
    parser.add_argument("--mode", default="bid_or_trade_flag", help="鎖板判斷模式")
    parser.add_argument("--max-events", type=int, default=20, help="每檔最多列印幾筆切換")
    parser.add_argument(
        "--limit-up",
        action="append",
        default=[],
        help="覆寫漲停價，格式 code=price，可重複帶多次，例如 --limit-up 6763=50.4",
    )
    args = parser.parse_args()

    path = Path(args.path).expanduser().resolve()
    mode = resolve_limit_up_mode(args.mode)
    overrides: Dict[str, Decimal] = {}
    for item in args.limit_up:
        raw = str(item or "").strip()
        if not raw or "=" not in raw:
            raise SystemExit(f"limit-up 參數格式錯誤：{raw!r}")
        code, price = raw.split("=", 1)
        overrides[code.strip()] = Decimal(price.strip())
    states = replay(path, args.code, mode, overrides or None)
    _print_report(states, mode, max(1, args.max_events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
