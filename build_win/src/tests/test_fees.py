"""
broker.fees / 成交回報 單元測試（Milestone 4）。
"""
import os
import sys
import unittest
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker import (  # noqa: E402
    FillEvent, MockAdapter, OrderSide,
    calc_fee, calc_tax, realized_pnl,
    FEE_DISCOUNT, MIN_FEE,
)


class TestCalcFee(unittest.TestCase):
    def test_min_fee(self):
        # 10 元 × 1 張 × 1000 × 0.1425% × 0.6 ≈ 8.55 → 取最低 20
        self.assertEqual(calc_fee(10, 1), MIN_FEE)

    def test_normal(self):
        # 100 元 × 5 張 × 1000 × 0.1425% × 0.6 = 427.5 → 427
        fee = calc_fee(100, 5)
        self.assertGreater(fee, MIN_FEE)
        self.assertEqual(fee, Decimal("427"))

    def test_no_discount(self):
        # 100 元 × 5 張 × 1000 × 0.1425% × 1.0 = 712.5 → 712
        fee = calc_fee(100, 5, discount=Decimal("1.0"))
        self.assertEqual(fee, Decimal("712"))


class TestCalcTax(unittest.TestCase):
    def test_normal(self):
        # 100 × 5 × 1000 × 0.3% = 1500
        self.assertEqual(calc_tax(100, 5), Decimal("1500"))

    def test_day_trade_half(self):
        # 100 × 5 × 1000 × 0.15% = 750
        self.assertEqual(calc_tax(100, 5, day_trade=True), Decimal("750"))


class TestRealizedPnL(unittest.TestCase):
    def test_profit(self):
        # 買 100 賣 110，2 張，當沖
        pnl = realized_pnl(100, 110, 2, day_trade=True)
        # 毛利 = (110-100) × 2000 = 20000
        self.assertEqual(pnl.gross, Decimal("20000"))
        # 稅 = 110 × 2000 × 0.0015 = 330
        self.assertEqual(pnl.tax, Decimal("330"))
        # net = 20000 - buy_fee - sell_fee - 330
        self.assertGreater(pnl.net, Decimal("19000"))
        self.assertLess(pnl.net, Decimal("20000"))

    def test_loss(self):
        pnl = realized_pnl(100, 90, 2, day_trade=True)
        self.assertLess(pnl.net, Decimal("0"))


class TestAdapterFillDispatch(unittest.TestCase):
    def test_mock_dispatch(self):
        m = MockAdapter()
        received = []
        m.on_filled(lambda ev: received.append(ev))
        ev = FillEvent(
            order_id="X1", code="2330", name="台積電", side=OrderSide.BUY,
            price=Decimal("1100"), qty=1, time=datetime.now(),
        )
        m.dispatch_fill(ev)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].code, "2330")

    def test_multi_subscribers(self):
        m = MockAdapter()
        a, b = [], []
        m.on_filled(lambda ev: a.append(ev))
        m.on_filled(lambda ev: b.append(ev))
        ev = FillEvent(order_id="X", code="2317", name="鴻海", side=OrderSide.SELL,
                       price=Decimal("220"), qty=2, time=datetime.now())
        m.dispatch_fill(ev)
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)


if __name__ == "__main__":
    unittest.main()
