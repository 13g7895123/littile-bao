"""
broker.account / scan_daily 單元測試（Milestone 6）。
"""
import os
import sys
import time
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker import (  # noqa: E402
    DEFAULT_MOCK_INFOS, MockAccountService, MockAdapter,
    OrderRequest, OrderSide, Position, ScanCriteria, scan_daily,
)


class TestScanDaily(unittest.TestCase):
    def test_default_filter_passes_normal(self):
        # 條件：寬鬆價格區間 + 排除處置 / 注意 / 限當沖
        crit = ScanCriteria(
            price_min=Decimal("0"), price_max=Decimal("99999"),
            min_prev_volume=0,
        )
        out = scan_daily(DEFAULT_MOCK_INFOS, crit)
        codes = {s.code for s in out}
        self.assertIn("2330", codes)
        self.assertNotIn("2454", codes)  # 處置股
        self.assertNotIn("2317", codes)  # 注意股
        self.assertNotIn("6505", codes)  # 限當沖

    def test_price_range_limits(self):
        crit = ScanCriteria(
            price_min=Decimal("100"), price_max=Decimal("300"),
            min_prev_volume=0,
        )
        out = scan_daily(DEFAULT_MOCK_INFOS, crit)
        for s in out:
            self.assertTrue(Decimal("100") <= s.limit_up_price <= Decimal("300"))

    def test_market_filter(self):
        crit = ScanCriteria(markets=("OTC",), min_prev_volume=0)
        out = scan_daily(DEFAULT_MOCK_INFOS, crit)
        for s in out:
            self.assertEqual(s.market, "OTC")

    def test_max_candidates(self):
        crit = ScanCriteria(max_candidates=3, min_prev_volume=0)
        out = scan_daily(DEFAULT_MOCK_INFOS, crit)
        self.assertLessEqual(len(out), 3)


class TestMockAccountService(unittest.TestCase):
    def test_snapshot_basic(self):
        svc = MockAccountService(initial_cash=Decimal("500000"))
        snap = svc.snapshot()
        self.assertEqual(snap.cash, Decimal("500000"))
        self.assertEqual(snap.buying_power, Decimal("500000"))
        self.assertEqual(len(snap.positions), 0)

    def test_set_positions_reflects(self):
        svc = MockAccountService()
        p = Position(code="2330", name="台積電", qty=2,
                     avg_cost=Decimal("1000"), last_price=Decimal("1050"),
                     market_value=Decimal("2100000"),
                     unrealized_pnl=Decimal("100000"),
                     unrealized_pnl_pct=Decimal("5"))
        svc.set_positions([p])
        snap = svc.snapshot()
        self.assertEqual(len(snap.positions), 1)
        self.assertEqual(snap.total_unrealized_pnl, Decimal("100000"))

    def test_polling(self):
        svc = MockAccountService()
        received = []
        svc.start_polling(received.append, interval=0.1)
        time.sleep(0.35)
        svc.stop()
        self.assertGreaterEqual(len(received), 2)


class TestMockAdapterAccountSync(unittest.TestCase):
    def test_fill_updates_positions(self):
        m = MockAdapter()
        m.login()
        svc = m.account_service()
        # 下買單 → 等成交 → 庫存應出現
        m.place_order(OrderRequest(
            code="2330", name="台積電",
            side=OrderSide.BUY, price=Decimal("1100"), qty=1,
        ))
        deadline = time.time() + 5.0
        while time.time() < deadline:
            snap = svc.snapshot()
            if snap.positions:
                break
            time.sleep(0.1)
        snap = svc.snapshot()
        self.assertEqual(len(snap.positions), 1)
        self.assertEqual(snap.positions[0].code, "2330")
        self.assertEqual(snap.positions[0].qty, 1)


if __name__ == "__main__":
    unittest.main()
