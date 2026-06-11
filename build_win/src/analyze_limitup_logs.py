"""
讀取盤中錄製檔，回推每種鎖漲停候選邏輯的觸發時間。

用法：
    python3 analyze_limitup_logs.py <session_ticks.ndjson.gz> [--code 2330]
"""
from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, Optional

from limitup_detection import LIMIT_UP_DETECTION_MODES, evaluate_limit_up_state


@dataclass
class SymbolState:
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
    effective_bid0_price: Optional[Decimal] = None
    effective_bid0_volume: int = 0
    has_ask_levels: bool = False
    has_bid_levels: bool = False
    prev_candidates: Dict[str, bool] = field(default_factory=dict)
    first_true_times: Dict[str, str] = field(default_factory=dict)
    true_counts: Dict[str, int] = field(default_factory=dict)
    first_signal_times: Dict[str, str] = field(default_factory=dict)


def _to_decimal(value) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _load_meta_map(ticks_path: Path) -> Dict[str, Decimal]:
    meta_name = ticks_path.name.replace(".ticks.ndjson.gz", ".meta.json").replace(".ticks.ndjson", ".meta.json")
    meta_path = ticks_path.with_name(meta_name)
    if not meta_path.exists():
        raise FileNotFoundError(f"找不到對應 meta.json：{meta_path}")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    mapping: Dict[str, Decimal] = {}
    for item in meta.get("symbol_universe", []) or []:
        code = str(item.get("code") or "").strip()
        limit_up = item.get("limit_up")
        if code and limit_up not in (None, ""):
            mapping[code] = Decimal(str(limit_up))
    return mapping


def _iter_lines(path: Path) -> Iterable[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:  # type: ignore[arg-type]
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def _event_time(row: dict) -> str:
    return str(row.get("api_time") or row.get("time") or row.get("t") or "")


def _apply_event(state: SymbolState, row: dict) -> None:
    kind = row.get("kind")
    if kind == "tick":
        state.last_price = _to_decimal(row.get("price"))
        state.trade_bid = _to_decimal(row.get("bid"))
        state.trade_ask = _to_decimal(row.get("ask"))
        state.trade_is_limit_up_price = row.get("is_limit_up_price")
        state.trade_is_limit_up_bid = row.get("is_limit_up_bid")
        state.trade_is_limit_up_ask = row.get("is_limit_up_ask")
    elif kind == "book":
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
        effective_bid = next(
            (
                level for level in bids
                if (_to_decimal(level.get("price")) or Decimal("0")) > 0
            ),
            None,
        )
        if effective_bid is not None:
            state.effective_bid0_price = _to_decimal(effective_bid.get("price"))
            state.effective_bid0_volume = int(effective_bid.get("volume") or 0)
        else:
            state.effective_bid0_price = None
            state.effective_bid0_volume = 0


def _evaluate(state: SymbolState, row: dict) -> None:
    result = evaluate_limit_up_state(
        limit_up=state.limit_up,
        ask0_price=state.ask0_price,
        ask0_volume=state.ask0_volume,
        bid0_price=state.bid0_price,
        bid0_volume=state.bid0_volume,
        last_price=state.last_price,
        trade_bid=state.trade_bid,
        trade_ask=state.trade_ask,
        effective_bid0_price=state.effective_bid0_price,
        effective_bid0_volume=state.effective_bid0_volume,
        has_ask_levels=state.has_ask_levels,
        has_bid_levels=state.has_bid_levels,
        is_limit_up_price=state.trade_is_limit_up_price,
        is_limit_up_bid=state.trade_is_limit_up_bid,
        is_limit_up_ask=state.trade_is_limit_up_ask,
    )
    stamp = _event_time(row)
    for key, value in result["signals"].items():
        if value and key not in state.first_signal_times:
            state.first_signal_times[key] = stamp
    for key, value in result["candidates"].items():
        prev = state.prev_candidates.get(key, False)
        if value and not prev:
            state.true_counts[key] = state.true_counts.get(key, 0) + 1
            state.first_true_times.setdefault(key, stamp)
        state.prev_candidates[key] = bool(value)


def analyze(path: Path, code_filter: Optional[str]) -> Dict[str, SymbolState]:
    limit_map = _load_meta_map(path)
    states: Dict[str, SymbolState] = {}
    for row in _iter_lines(path):
        code = str(row.get("code") or "").strip()
        kind = row.get("kind")
        if code_filter and code != code_filter:
            continue
        if kind not in {"tick", "book"}:
            continue
        limit_up = limit_map.get(code)
        if limit_up is None:
            continue
        state = states.setdefault(code, SymbolState(limit_up=limit_up))
        _apply_event(state, row)
        _evaluate(state, row)
    return states


def _print_report(states: Dict[str, SymbolState]) -> None:
    if not states:
        print("沒有可分析的 tick/book 資料。")
        return
    for code in sorted(states):
        state = states[code]
        print(f"=== {code} limit_up={state.limit_up} ===")
        print("signals:")
        for name in sorted(state.first_signal_times):
            print(f"  {name}: first={state.first_signal_times[name]}")
        print("candidates:")
        for mode in LIMIT_UP_DETECTION_MODES:
            first = state.first_true_times.get(mode, "-")
            count = state.true_counts.get(mode, 0)
            desc = LIMIT_UP_DETECTION_MODES[mode]
            print(f"  {mode}: first={first} count={count} desc={desc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="分析富邦錄製檔中的鎖漲停候選邏輯")
    parser.add_argument("path", help="session_*.ticks.ndjson.gz 或 .ndjson")
    parser.add_argument("--code", help="只分析單一股票代號", default="")
    args = parser.parse_args()

    path = Path(args.path).expanduser().resolve()
    states = analyze(path, args.code.strip() or None)
    _print_report(states)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
