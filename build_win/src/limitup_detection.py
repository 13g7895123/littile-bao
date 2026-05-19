"""
limitup_detection.py - 鎖漲停候選邏輯與欄位判斷。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional


LIMIT_UP_DETECTION_MODES: Dict[str, str] = {
    "ask_or_bid_or_last": "ask1=漲停 或 bid1=漲停 或 最新成交=漲停",
    "ask_only": "只有 ask1=漲停 才算封板",
    "bid_only": "只有 bid1=漲停 才算鎖板",
    "bid_or_trade_flag": "bid1=漲停 或 API 的 isLimitUpBid=true",
    "bid_and_last": "bid1=漲停 且 最新成交=漲停",
    "bid_and_no_ask": "bid1=漲停 且 沒有任何委賣檔",
    "bid_and_zero_ask": "bid1=漲停 且 沒有委賣或賣一量=0",
    "trade_price_only": "只有最新成交=漲停 才算觸板/封板",
    "trade_flag_only": "只有 API 漲停旗標為真才算",
}

DEFAULT_LIMIT_UP_DETECTION_MODE = "ask_or_bid_or_last"


def _to_decimal(value: Optional[Decimal]) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def evaluate_limit_up_state(
    *,
    limit_up: Decimal,
    ask0_price: Optional[Decimal],
    ask0_volume: int,
    bid0_price: Optional[Decimal],
    bid0_volume: int,
    last_price: Optional[Decimal],
    trade_bid: Optional[Decimal] = None,
    trade_ask: Optional[Decimal] = None,
    has_ask_levels: bool = False,
    has_bid_levels: bool = False,
    is_limit_up_price: Optional[bool] = None,
    is_limit_up_bid: Optional[bool] = None,
    is_limit_up_ask: Optional[bool] = None,
) -> dict:
    limit_up = Decimal(str(limit_up))
    ask0_price = _to_decimal(ask0_price)
    bid0_price = _to_decimal(bid0_price)
    last_price = _to_decimal(last_price)
    trade_bid = _to_decimal(trade_bid)
    trade_ask = _to_decimal(trade_ask)

    ask_at_limit = ask0_price is not None and ask0_price >= limit_up
    bid_at_limit = bid0_price is not None and bid0_price >= limit_up
    last_at_limit = last_price is not None and last_price >= limit_up
    trade_bid_at_limit = trade_bid is not None and trade_bid >= limit_up
    trade_ask_at_limit = trade_ask is not None and trade_ask >= limit_up
    ask_empty = not has_ask_levels
    bid_empty = not has_bid_levels
    ask_qty_zero = ask_empty or int(ask0_volume or 0) <= 0
    bid_qty_positive = (not bid_empty) and int(bid0_volume or 0) > 0
    trade_flag_price = bool(is_limit_up_price)
    trade_flag_bid = bool(is_limit_up_bid)
    trade_flag_ask = bool(is_limit_up_ask)
    trade_at_ask = (
        last_price is not None
        and trade_ask is not None
        and last_price == trade_ask
    )
    trade_at_bid = (
        last_price is not None
        and trade_bid is not None
        and last_price == trade_bid
    )

    candidates = {
        "ask_or_bid_or_last": ask_at_limit or bid_at_limit or last_at_limit,
        "ask_only": ask_at_limit,
        "bid_only": bid_at_limit,
        "bid_or_trade_flag": bid_at_limit or trade_flag_bid or trade_bid_at_limit,
        "bid_and_last": bid_at_limit and last_at_limit,
        "bid_and_no_ask": bid_at_limit and ask_empty,
        "bid_and_zero_ask": bid_at_limit and ask_qty_zero,
        "trade_price_only": last_at_limit or trade_flag_price,
        "trade_flag_only": trade_flag_price or trade_flag_bid or trade_flag_ask,
    }

    return {
        "ask_qty_at_limit": int(ask0_volume or 0) if ask_at_limit else 0,
        "signals": {
            "ask_at_limit": ask_at_limit,
            "bid_at_limit": bid_at_limit,
            "last_at_limit": last_at_limit,
            "trade_bid_at_limit": trade_bid_at_limit,
            "trade_ask_at_limit": trade_ask_at_limit,
            "trade_flag_price": trade_flag_price,
            "trade_flag_bid": trade_flag_bid,
            "trade_flag_ask": trade_flag_ask,
            "trade_at_ask": trade_at_ask,
            "trade_at_bid": trade_at_bid,
            "ask_empty": ask_empty,
            "bid_empty": bid_empty,
            "ask_qty_zero": ask_qty_zero,
            "bid_qty_positive": bid_qty_positive,
        },
        "candidates": candidates,
    }


def resolve_limit_up_mode(mode: str) -> str:
    mode = str(mode or "").strip()
    if mode in LIMIT_UP_DETECTION_MODES:
        return mode
    return DEFAULT_LIMIT_UP_DETECTION_MODE
