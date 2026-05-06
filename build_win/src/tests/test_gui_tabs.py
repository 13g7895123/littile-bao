"""
GUI 分頁配置測試。
"""
import os
import sys
import unittest
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None

import gui  # noqa: E402


class _Value:
    def __init__(self, value: str):
        self.value = value


@unittest.skipIf(QApplication is None, "PyQt6 is not installed")
class TestGuiTabLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.win = gui.App()
        self.addCleanup(self._cleanup_window)

    def _cleanup_window(self):
        for attr in ("_log_timer", "_monitor_timer"):
            timer = getattr(self.win, attr, None)
            if timer is not None:
                timer.stop()
        self.win.close()

    def _is_descendant(self, child, parent) -> bool:
        widget = child
        while widget is not None:
            if widget is parent:
                return True
            widget = widget.parentWidget()
        return False

    def test_body_contains_only_tab_pages_container(self):
        root_lay = self.win.centralWidget().layout()
        body = root_lay.itemAt(1).widget()

        self.assertEqual(body.layout().count(), 1)

    def test_strategy_settings_are_inside_settings_tab(self):
        self.win._switch_tab("settings")

        self.assertFalse(self.win._pages["settings"].isHidden())
        self.assertTrue(self.win._pages["dashboard"].isHidden())
        self.assertIn("per_stock_amount", self.win._fields)
        self.assertTrue(
            self._is_descendant(
                self.win._fields["per_stock_amount"],
                self.win._pages["settings"],
            )
        )

    def test_dashboard_keeps_only_stats_and_monitor_sections(self):
        self.assertTrue(
            self._is_descendant(self.win.monitor_table, self.win._pages["dashboard"])
        )
        self.assertFalse(
            self._is_descendant(self.win.orders_table, self.win._pages["dashboard"])
        )
        self.assertFalse(
            self._is_descendant(self.win.trades_table, self.win._pages["dashboard"])
        )
        self.assertFalse(
            self._is_descendant(self.win.positions_table, self.win._pages["dashboard"])
        )
        self.assertFalse(
            self._is_descendant(self.win.event_log, self.win._pages["dashboard"])
        )

    def test_tables_and_log_update_their_own_tabs(self):
        order = SimpleNamespace(
            order_id="DRYTEST001",
            code="2330",
            name="台積電",
            side=_Value("BUY"),
            status=_Value("PENDING"),
            price=Decimal("100"),
            qty=1,
            source="DRY",
        )
        self.win._append_order(order)
        self.assertEqual(self.win.orders_full_table.rowCount(), 1)
        self.assertTrue(
            self._is_descendant(self.win.orders_full_table, self.win._pages["orders"])
        )

        order.status = _Value("FILLED")
        self.win._append_order(order)
        self.assertEqual(self.win.orders_full_table.rowCount(), 1)
        self.assertEqual(self.win.orders_full_table.item(0, 5).text(), "已成交")

        self.win._append_trade({
            "time": "09:01:00",
            "code": "2330",
            "name": "台積電",
            "action": "BUY",
            "price": 100.0,
            "qty": 1,
        })
        self.assertEqual(self.win.trades_full_table.rowCount(), 1)

        self.win._append_log("INFO", "tab log smoke")
        self.assertIn("tab log smoke", self.win.events_full_log.toPlainText())
        self.assertTrue(
            self._is_descendant(self.win.events_full_log, self.win._pages["events"])
        )


if __name__ == "__main__":
    unittest.main()