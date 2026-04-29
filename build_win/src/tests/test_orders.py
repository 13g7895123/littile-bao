"""
broker.orders 單元測試（Milestone 5）。
"""
import os
import sys
import threading
import time
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker import (  # noqa: E402
    FubonAdapter, MockAdapter, OrderRequest, OrderSide, OrderStatus,
    FubonOrderManager, MockOrderManager,
)
from broker.errors import FubonNotLoggedInError  # noqa: E402


class TestOrderRequest(unittest.TestCase):
    def test_qty_must_positive(self):
        with self.assertRaises(ValueError):
            OrderRequest(code="2330", price=Decimal("100"), qty=0)

    def test_limit_requires_price(self):
        with self.assertRaises(ValueError):
            OrderRequest(code="2330", price=Decimal("0"), qty=1, order_type="LIMIT")


class TestMockOrderFlow(unittest.TestCase):
    def setUp(self):
        self.adapter = MockAdapter()
        self.adapter.login()
        # 為求測試穩定，用較短且固定的延遲
        self.adapter._order_mgr = MockOrderManager(self.adapter, fill_delay_range=(0.2, 0.4))
        self.orders = []
        self.fills = []
        self.adapter.on_order(self.orders.append)
        self.adapter.on_filled(self.fills.append)

    def test_buy_pending_then_filled(self):
        oid = self.adapter.place_order(OrderRequest(
            code="2330", name="台積電",
            side=OrderSide.BUY, price=Decimal("1100"), qty=1,
        ))
        self.assertTrue(oid)

        # 等待最大 fill_delay (1.8s) + 緩衝
        deadline = time.time() + 5.0
        while time.time() < deadline and not self.fills:
            time.sleep(0.1)

        self.assertGreaterEqual(len(self.orders), 2)  # PENDING + FILLED
        self.assertEqual(self.orders[0].status, OrderStatus.PENDING)
        self.assertEqual(self.orders[-1].status, OrderStatus.FILLED)
        self.assertEqual(len(self.fills), 1)
        self.assertEqual(self.fills[0].code, "2330")
        self.assertEqual(self.fills[0].side, OrderSide.BUY)

    def test_cancel_before_fill(self):
        # 建立超長延遲的 manager 確保來得及取消
        mgr = MockOrderManager(self.adapter, fill_delay_range=(2.0, 2.0))
        self.adapter._order_mgr = mgr

        oid = self.adapter.place_order(OrderRequest(
            code="2317", name="鴻海",
            side=OrderSide.BUY, price=Decimal("220"), qty=1,
        ))
        ok = self.adapter.cancel_order(oid)
        self.assertTrue(ok)
        statuses = [o.status for o in self.orders]
        self.assertIn(OrderStatus.PENDING, statuses)
        self.assertIn(OrderStatus.CANCELLED, statuses)
        # 未產生成交
        time.sleep(2.5)
        self.assertEqual(len(self.fills), 0)


class TestFubonDryRun(unittest.TestCase):
    def _make(self, dry_run: bool) -> FubonAdapter:
        return FubonAdapter(
            personal_id="A123", password="p",
            cert_path="/tmp/cert.pfx", cert_password="x",
            branch_no="9000", account_no="1234567",
            dry_run=dry_run,
        )

    def test_place_without_login_raises(self):
        adp = self._make(dry_run=True)
        with self.assertRaises(FubonNotLoggedInError):
            adp.place_order(OrderRequest(
                code="2330", price=Decimal("1100"), qty=1,
            ))

    def test_dry_run_emits_pending_no_sdk(self):
        adp = self._make(dry_run=True)
        # 偽造已連線狀態（不觸發真實登入）
        from broker.models import ConnectionState
        adp._state = ConnectionState.CONNECTED
        events = []
        adp.on_order(events.append)
        oid = adp.place_order(OrderRequest(code="2330", price=Decimal("1100"), qty=1))
        self.assertTrue(oid.startswith("DRY"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, OrderStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
