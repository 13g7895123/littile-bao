"""
GUI 分頁配置測試。
"""
import os
import sys
import threading
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
        self.assertGreater(self.win._strategy_settings_panel.maximumWidth(), 1000)

    def test_dashboard_preserves_original_summary_sections(self):
        self.assertTrue(
            self._is_descendant(
                self.win._fields["per_stock_amount"],
                self.win._pages["dashboard"],
            )
        )
        self.assertLessEqual(self.win._strategy_settings_panel.maximumWidth(), 320)
        self.assertTrue(
            self._is_descendant(self.win.monitor_table, self.win._pages["dashboard"])
        )
        self.assertTrue(
            self._is_descendant(self.win.orders_table, self.win._pages["dashboard"])
        )
        self.assertTrue(
            self._is_descendant(self.win.trades_table, self.win._pages["dashboard"])
        )
        self.assertTrue(
            self._is_descendant(self.win.positions_table, self.win._pages["dashboard"])
        )
        self.assertTrue(
            self._is_descendant(self.win.event_log, self.win._pages["dashboard"])
        )
        self.assertTrue(
            self._is_descendant(self.win.orders_full_table, self.win._pages["orders"])
        )
        self.assertTrue(
            self._is_descendant(self.win.trades_full_table, self.win._pages["orders"])
        )
        self.assertTrue(
            self._is_descendant(self.win.positions_full_table, self.win._pages["positions"])
        )
        self.assertTrue(
            self._is_descendant(self.win.events_full_log, self.win._pages["events"])
        )
        self.assertIsNot(self.win.orders_table, self.win.orders_full_table)
        self.assertIsNot(self.win.trades_table, self.win.trades_full_table)
        self.assertIsNot(self.win.positions_table, self.win.positions_full_table)
        self.assertIsNot(self.win.event_log, self.win.events_full_log)

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
        self.assertEqual(self.win.orders_table.rowCount(), 1)
        self.assertEqual(self.win.orders_full_table.rowCount(), 1)
        self.assertTrue(
            self._is_descendant(self.win.orders_full_table, self.win._pages["orders"])
        )

        order.status = _Value("FILLED")
        self.win._append_order(order)
        self.assertEqual(self.win.orders_table.rowCount(), 1)
        self.assertEqual(self.win.orders_full_table.rowCount(), 1)
        self.assertEqual(self.win.orders_table.item(0, 5).text(), "已成交")
        self.assertEqual(self.win.orders_full_table.item(0, 5).text(), "已成交")

        self.win._switch_tab("orders")
        self.assertEqual(self.win.orders_full_table.rowCount(), 1)

        self.win._append_trade({
            "time": "09:01:00",
            "code": "2330",
            "name": "台積電",
            "action": "BUY",
            "price": 100.0,
            "qty": 1,
        })
        self.assertEqual(self.win.trades_table.rowCount(), 1)
        self.assertEqual(self.win.trades_full_table.rowCount(), 1)

        self.win._append_log("INFO", "tab log smoke")
        self.assertIn("tab log smoke", self.win.event_log.toPlainText())
        self.assertIn("tab log smoke", self.win.events_full_log.toPlainText())
        self.assertTrue(
            self._is_descendant(self.win.events_full_log, self.win._pages["events"])
        )

    def test_after_close_fubon_preview_uses_close_price_range(self):
        class FakeSnapshot:
            def __init__(self):
                self.calls = []

            def quotes(self, **kwargs):
                self.calls.append(kwargs)
                market = kwargs.get("market")
                data = {
                    "TSE": [
                        {
                            "symbol": "2330",
                            "name": "台積電",
                            "previousClose": "90",
                            "closePrice": "88.5",
                            "tradeVolume": "1",
                        },
                        {
                            "symbol": "2317",
                            "name": "鴻海",
                            "previousClose": "110",
                            "closePrice": "120",
                            "tradeVolume": "1",
                        },
                    ],
                    "OTC": [
                        {
                            "symbol": "4919",
                            "name": "新唐",
                            "previousClose": "50",
                            "closePrice": "55",
                            "tradeVolume": "1",
                        },
                    ],
                }
                return {"data": data.get(market, [])}

        class FakeSdk:
            def __init__(self, snapshot):
                self.marketdata = SimpleNamespace(
                    rest_client=SimpleNamespace(
                        stock=SimpleNamespace(snapshot=snapshot)
                    )
                )

            def init_realtime(self):
                return None

        snapshot = FakeSnapshot()
        sdk = FakeSdk(snapshot)
        broker = SimpleNamespace(_sdk=sdk, sdk=sdk)
        self.win._fields["price_min"].setText("80")
        self.win._fields["price_max"].setText("90")
        self.win._fields["daily_volume_min"].setText("999999")
        self.win._checks["market_twse"].setChecked(True)
        self.win._checks["market_tpex"].setChecked(True)
        self.win._is_after_market_close = lambda: True

        summary = self.win._load_dashboard_preview_summary(
            broker, self.win._collect_config())

        self.assertEqual([item["code"] for item in summary], ["2330"])
        self.assertEqual(summary[0]["price"], 88.5)
        self.assertEqual(snapshot.calls[0], {"market": "TSE", "type": "COMMONSTOCK"})

    def test_fubon_strategy_start_loads_in_background_and_can_cancel(self):
        class BlockingSnapshot:
            def __init__(self):
                self.entered = threading.Event()
                self.release = threading.Event()

            def quotes(self, **_kwargs):
                self.entered.set()
                self.release.wait(1.0)
                return {"data": []}

        class FakeSdk:
            def __init__(self, snapshot):
                self.marketdata = SimpleNamespace(
                    rest_client=SimpleNamespace(
                        stock=SimpleNamespace(snapshot=snapshot)
                    )
                )

            def init_realtime(self):
                return None

        class FakeBroker:
            def __init__(self, sdk):
                self._sdk = sdk
                self.sdk = sdk

            def create_realtime_feed(self):
                return None

        snapshot = BlockingSnapshot()
        broker = FakeBroker(FakeSdk(snapshot))
        self.win.broker = broker
        self.win._is_after_market_close = lambda: False
        self.win._checks["market_twse"].setChecked(True)
        self.win._checks["market_tpex"].setChecked(False)

        self.win._start_trading()

        self.assertTrue(snapshot.entered.wait(1.0))
        self.assertTrue(self.win._strategy_starting)
        self.assertFalse(self.win._running)
        self.assertIn("載入中", self.win.strategy_status_lbl.text())

        self.win._stop_trading()
        snapshot.release.set()
        self.assertFalse(self.win._strategy_starting)
        self.assertFalse(self.win._running)

    def test_after_close_strategy_start_uses_market_snapshot(self):
        class FakeSnapshot:
            def __init__(self):
                self.calls = []

            def quotes(self, **kwargs):
                self.calls.append(kwargs)
                self.assertNotIn("symbols", kwargs)
                return {"data": [{
                    "symbol": "2330",
                    "name": "台積電",
                    "previousClose": "90",
                    "closePrice": "88.5",
                    "tradeVolume": "2000",
                }]}

            def assertNotIn(self, key, values):
                if key in values:
                    raise AssertionError(f"unexpected {key} call")

        class FakeSdk:
            def __init__(self, snapshot):
                self.marketdata = SimpleNamespace(
                    rest_client=SimpleNamespace(
                        stock=SimpleNamespace(snapshot=snapshot)
                    )
                )

            def init_realtime(self):
                return None

        class FakeBroker:
            def __init__(self, sdk):
                self._sdk = sdk
                self.sdk = sdk

            def create_realtime_feed(self):
                return None

        snapshot = FakeSnapshot()
        self.win.broker = FakeBroker(FakeSdk(snapshot))
        self.win._is_after_market_close = lambda: True
        self.win._checks["market_twse"].setChecked(True)
        self.win._checks["market_tpex"].setChecked(False)
        self.win._fields["daily_volume_min"].setText("1")

        symbol_infos, feed = self.win._load_trading_runtime(
            self.win.broker, self.win._collect_config())

        self.assertIsNone(feed)
        self.assertEqual(snapshot.calls[0], {"market": "TSE", "type": "COMMONSTOCK"})
        self.assertEqual(list(symbol_infos.keys()), ["2330"])


if __name__ == "__main__":
    unittest.main()