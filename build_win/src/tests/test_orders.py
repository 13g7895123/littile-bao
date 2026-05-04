"""
broker.orders 單元測試（Milestone 5）。
"""
import json
import os
import sys
import threading
import tempfile
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

    def test_dry_run_emits_pending_then_filled_and_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adp = self._make(dry_run=True)
            from broker.models import ConnectionState
            adp._state = ConnectionState.CONNECTED
            adp.dry_run_fill_min_sec = 0.0
            adp.dry_run_fill_max_sec = 0.0
            adp.dry_run_audit_dir = tmpdir
            events = []
            fills = []
            adp.on_order(events.append)
            adp.on_filled(fills.append)

            oid = adp.place_order(OrderRequest(
                code="2330", name="台積電",
                price=Decimal("1100"), qty=1,
            ))
            self.assertTrue(oid.startswith("DRY"))

            deadline = time.time() + 2.0
            while time.time() < deadline and not fills:
                time.sleep(0.05)

            self.assertGreaterEqual(len(events), 2)
            self.assertEqual(events[0].status, OrderStatus.PENDING)
            self.assertEqual(events[-1].status, OrderStatus.FILLED)
            self.assertEqual(events[0].source, "DRY")
            self.assertEqual(len(fills), 1)
            self.assertEqual(fills[0].price, Decimal("1100"))

            logs = [p for p in os.listdir(tmpdir) if p.startswith("dry_run_audit_")]
            self.assertEqual(len(logs), 1)
            with open(os.path.join(tmpdir, logs[0]), "r", encoding="utf-8") as f:
                records = [json.loads(line) for line in f]
            self.assertEqual([r["type"] for r in records], ["PLACE", "FILL"])
            self.assertEqual(records[0]["source"], "DRY")

    def test_dry_run_cancel_writes_cancel_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adp = self._make(dry_run=True)
            from broker.models import ConnectionState
            adp._state = ConnectionState.CONNECTED
            adp.dry_run_fill_min_sec = 1.0
            adp.dry_run_fill_max_sec = 1.0
            adp.dry_run_audit_dir = tmpdir
            events = []
            fills = []
            adp.on_order(events.append)
            adp.on_filled(fills.append)

            oid = adp.place_order(OrderRequest(
                code="2317", name="鴻海",
                price=Decimal("220"), qty=1,
            ))
            self.assertTrue(adp.cancel_order(oid))
            time.sleep(1.2)

            statuses = [e.status for e in events]
            self.assertIn(OrderStatus.PENDING, statuses)
            self.assertIn(OrderStatus.CANCELLED, statuses)
            self.assertEqual(len(fills), 0)

            logs = [p for p in os.listdir(tmpdir) if p.startswith("dry_run_audit_")]
            with open(os.path.join(tmpdir, logs[0]), "r", encoding="utf-8") as f:
                records = [json.loads(line) for line in f]
            self.assertEqual([r["type"] for r in records], ["PLACE", "CANCEL"])


if __name__ == "__main__":
    unittest.main()
