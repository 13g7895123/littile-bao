"""
broker.fees — 台股手續費 / 證交稅 / 損益計算

費率參考：
    手續費：0.1425%（買賣雙邊收取），多數券商給折扣 0.6（可由設定調整），
            最低 20 元
    證交稅：0.3%（賣出收取），現股當沖減半 0.15%
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Union

Number = Union[int, float, Decimal]

FEE_RATE: Decimal = Decimal("0.001425")
FEE_DISCOUNT: Decimal = Decimal("0.6")        # 預設 6 折，可由設定調整
MIN_FEE: Decimal = Decimal("20")
TAX_RATE: Decimal = Decimal("0.003")
TAX_RATE_DAYTRADE: Decimal = Decimal("0.0015")


def _to_decimal(x: Number) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def calc_fee(price: Number, qty_lots: int, discount: Number = FEE_DISCOUNT) -> Decimal:
    """
    計算單邊手續費（台股一張 = 1000 股）。
    依券商折扣後不足 20 元時收最低 20 元。
    """
    p = _to_decimal(price)
    d = _to_decimal(discount)
    raw = p * Decimal(qty_lots) * Decimal("1000") * FEE_RATE * d
    fee = raw.quantize(Decimal("1"), rounding=ROUND_DOWN)  # 元（無條件捨去到整數）
    return max(fee, MIN_FEE) if qty_lots > 0 else Decimal("0")


def calc_tax(price: Number, qty_lots: int, day_trade: bool = False) -> Decimal:
    """
    計算證交稅（賣出收取，當沖減半）。
    """
    p = _to_decimal(price)
    rate = TAX_RATE_DAYTRADE if day_trade else TAX_RATE
    raw = p * Decimal(qty_lots) * Decimal("1000") * rate
    return raw.quantize(Decimal("1"), rounding=ROUND_DOWN)


@dataclass
class TradePnL:
    gross: Decimal       # 賣出收入 - 買進成本（不計手續費 / 稅）
    buy_fee: Decimal
    sell_fee: Decimal
    tax: Decimal
    net: Decimal         # 已扣手續費與稅後淨損益


def realized_pnl(
    buy_price: Number,
    sell_price: Number,
    qty_lots: int,
    day_trade: bool = False,
    fee_discount: Number = FEE_DISCOUNT,
) -> TradePnL:
    """
    計算單檔買→賣實現損益（含手續費、證交稅）。
    """
    bp = _to_decimal(buy_price)
    sp = _to_decimal(sell_price)
    shares = Decimal(qty_lots) * Decimal("1000")
    gross = (sp - bp) * shares
    buy_fee = calc_fee(bp, qty_lots, fee_discount)
    sell_fee = calc_fee(sp, qty_lots, fee_discount)
    tax = calc_tax(sp, qty_lots, day_trade)
    net = gross - buy_fee - sell_fee - tax
    return TradePnL(gross=gross, buy_fee=buy_fee, sell_fee=sell_fee, tax=tax, net=net)
