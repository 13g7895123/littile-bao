"""
GUI 分頁配置測試。
"""
import os
import sys
import threading
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

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
        self.assertTrue(
            self._is_descendant(self.win.limitup_test_stock_table, self.win._pages["limitup_test"])
        )
        self.assertTrue(
            self._is_descendant(self.win.limitup_test_mode_table, self.win._pages["limitup_test"])
        )
        self.assertTrue(
            self._is_descendant(self.win.strategy_trigger_table, self.win._pages["events"])
        )
        self.assertTrue(
            self._is_descendant(self.win.decision_detail_table, self.win._pages["decision_detail"])
        )
        self.assertFalse(self.win._tab_btns["decision_detail"].isHidden())
        self.assertIsNot(self.win.orders_table, self.win.orders_full_table)
        self.assertIsNot(self.win.trades_table, self.win.trades_full_table)
        self.assertIsNot(self.win.positions_table, self.win.positions_full_table)
        self.assertIsNot(self.win.event_log, self.win.events_full_log)

    def test_strategy_settings_collect_new_buy_sell_groups(self):
        self.assertIn("consume_qty_threshold", self.win._fields)
        self.assertIn("f4_open_ticks_to_sell", self.win._fields)
        self.assertIn("consume_enabled", self.win._checks)
        self.assertIn("f4_require_today_limitup", self.win._checks)
        self.assertTrue(hasattr(self.win, "sell_all_strategy_btn"))

        self.win._fields["consume_qty_threshold"].setText("321")
        self.win._fields["f4_open_ticks_to_sell"].setText("2")
        self.win._checks["consume_enabled"].setChecked(True)
        self.win._checks["consume_mutex_with_f1"].setChecked(False)
        self.win._checks["f4_require_today_limitup"].setChecked(False)
        self.win._checks["excl_open_limit"].setChecked(True)
        self.win._checks["excl_sealed"].setChecked(False)

        cfg = self.win._collect_config()

        self.assertTrue(cfg.f_consume_enabled)
        self.assertEqual(cfg.consume_qty_threshold, 321)
        self.assertFalse(cfg.consume_mutex_with_f1)
        self.assertEqual(cfg.f4_open_ticks_to_sell, 2)
        self.assertFalse(cfg.f4_require_today_limitup)
        self.assertFalse(cfg.f_open_limitup_entry_enabled)
        self.assertFalse(cfg.f12_enabled)

    def test_strategy_trigger_events_render_to_events_page(self):
        self.win._append_strategy_event({
            "time": "09:01:02",
            "side": "BUY",
            "code": "2330",
            "name": "台積電",
            "strategy": "F1+F7+F10",
            "details": {"ask_qty": "20", "candle": "1"},
        })

        self.assertEqual(self.win.strategy_trigger_table.rowCount(), 1)
        self.assertEqual(self.win.strategy_trigger_table.item(0, 1).text(), "2330")
        self.assertEqual(self.win.strategy_trigger_table.item(0, 3).text(), "買入")
        self.assertIn("ask_qty=20", self.win.strategy_trigger_table.item(0, 5).text())
        self.assertEqual(self.win.strategy_trigger_summary_lbl.text(), "共 1 筆")

    def test_decision_detail_tab_can_be_shown_and_receives_events(self):
        self.assertFalse(self.win._tab_btns["decision_detail"].isHidden())

        self.win._toggle_decision_detail_tab()

        self.assertTrue(self.win._tab_btns["decision_detail"].isHidden())
        self.assertTrue(self.win._pages["decision_detail"].isHidden())

        self.win._toggle_decision_detail_tab()

        self.assertFalse(self.win._tab_btns["decision_detail"].isHidden())
        self.assertFalse(self.win._pages["decision_detail"].isHidden())

        self.win._append_decision_detail({
            "time": "09:01:02",
            "code": "2330",
            "name": "台積電",
            "category": "ENTRY_SKIP",
            "result": "未進場",
            "reason": "F1:委賣 120 ≥ 100 張",
            "details": {"ask_qty": 120, "candle": 1, "last_1s_vol": 33},
        })

        self.assertEqual(self.win.decision_detail_table.rowCount(), 1)
        self.assertEqual(self.win.decision_detail_table.item(0, 1).text(), "2330")
        self.assertEqual(self.win.decision_detail_table.item(0, 4).text(), "未進場")
        self.assertIn("ask_qty=120", self.win.decision_detail_table.item(0, 6).text())

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
            time=datetime(2026, 5, 20, 9, 1, 2),
        )
        self.win._append_order(order)
        self.assertEqual(self.win.orders_table.rowCount(), 1)
        self.assertEqual(self.win.orders_full_table.rowCount(), 1)
        self.assertEqual(self.win.orders_table.item(0, 5).text(), "09:01:02")
        self.assertEqual(self.win.orders_table.item(0, 6).text(), "")
        self.assertTrue(
            self._is_descendant(self.win.orders_full_table, self.win._pages["orders"])
        )

        order.status = _Value("FILLED")
        order.time = datetime(2026, 5, 20, 9, 1, 5)
        self.win._append_order(order)
        self.assertEqual(self.win.orders_table.rowCount(), 1)
        self.assertEqual(self.win.orders_full_table.rowCount(), 1)
        self.assertEqual(self.win.orders_table.item(0, 6).text(), "09:01:05")
        self.assertEqual(self.win.orders_table.item(0, 7).text(), "已成交")
        self.assertEqual(self.win.orders_full_table.item(0, 6).text(), "09:01:05")
        self.assertEqual(self.win.orders_full_table.item(0, 7).text(), "已成交")

        self.win._switch_tab("orders")
        self.assertEqual(self.win.orders_full_table.rowCount(), 1)

        self.win._append_trade({
            "time": "09:01:00",
            "detail_time": "2026-05-20T09:01:00",
            "code": "2330",
            "name": "台積電",
            "action": "BUY",
            "price": 100.0,
            "qty": 1,
        })
        self.win._append_trade({
            "time": "09:03:00",
            "detail_time": "2026-05-20T09:03:00",
            "code": "2330",
            "name": "台積電",
            "action": "SELL",
            "price": 101.0,
            "qty": 1,
            "pnl": 500.0,
        })
        self.assertEqual(self.win.trades_table.rowCount(), 2)
        self.assertEqual(self.win.trades_full_table.rowCount(), 2)
        self.assertIn("時間=2026-05-20T09:03:00", self.win.trades_table.item(0, 6).text())
        self.assertIn("數量=1", self.win.trades_full_table.item(0, 6).text())
        self.assertEqual(self.win.trades_table.item(0, 7).text(), "+500")
        self.assertEqual(self.win.stat_trade_cnt.text(), f"1 / {self.win.cfg.daily_max_trades}")

        self.win._set_log_filter("all")
        self.win._append_log("INFO", "tab log smoke")
        self.assertIn("tab log smoke", self.win.event_log.toPlainText())
        self.assertIn("tab log smoke", self.win.events_full_log.toPlainText())

    def test_socket_disconnect_auto_restarts_without_prompt(self):
        self.win._running = True
        self.win._strategy_starting = False
        self.win._socket_recovering = False
        self.win._toggles["strategy_enabled"] = mock.Mock()

        with mock.patch.object(gui.QMessageBox, "warning") as warning_mock, \
             mock.patch.object(gui.QTimer, "singleShot") as timer_mock, \
             mock.patch.object(self.win, "_stop_trading") as stop_mock, \
             mock.patch.object(self.win, "_set_strategy_status") as status_mock, \
             mock.patch.object(self.win, "_start_trading") as start_mock, \
             mock.patch.object(gui, "push_log") as push_log_mock:
            self.win._handle_feed_disconnect_ui("socket closed")

            warning_mock.assert_not_called()
            stop_mock.assert_called_once()
            status_mock.assert_called_once_with("斷線重啟中…", gui.C["yellow_l"])
            timer_mock.assert_called_once()
            self.assertEqual(timer_mock.call_args.args[0], 1200)

            messages = [call.args[1] for call in push_log_mock.call_args_list]
            self.assertTrue(any("偵測到 socket 中斷" in message for message in messages))
            self.assertTrue(any("socket 斷線已進入自動重連流程" in message for message in messages))

            restart_cb = timer_mock.call_args.args[1]
            restart_cb()

            start_mock.assert_called_once()
            self.win._toggles["strategy_enabled"].set.assert_called_once_with(True)
            self.assertFalse(self.win._socket_recovering)

    def test_return_rate_uses_realized_and_unrealized_pnl(self):
        self.win._append_trade({
            "time": "09:03:00",
            "detail_time": "2026-05-20T09:03:00",
            "code": "2330",
            "name": "台積電",
            "action": "SELL",
            "price": 101.0,
            "qty": 1,
            "pnl": 500.0,
            "cost_basis": 100000.0,
        })

        snap = SimpleNamespace(
            positions=[
                SimpleNamespace(
                    code="2317",
                    name="鴻海",
                    qty=1,
                    avg_cost=Decimal("50"),
                    last_price=Decimal("50.3"),
                    unrealized_pnl=Decimal("300"),
                    unrealized_pnl_pct=Decimal("0.6"),
                )
            ],
            buying_power=Decimal("250000"),
        )
        self.win._render_account(snap)

        self.assertEqual(self.win.stat_realized.text(), "+500")
        self.assertEqual(self.win.stat_pnl_today.text(), "+800")
        self.assertEqual(self.win.stat_return.text(), "+0.53%")

    def test_event_log_defaults_to_strategy_filter_and_hides_non_strategy_logs(self):
        self.assertEqual(self.win._log_filter, "strategy")

        self.win._append_log("INFO", "一般系統訊息")
        self.assertNotIn("一般系統訊息", self.win.event_log.toPlainText())
        self.assertNotIn("一般系統訊息", self.win.events_full_log.toPlainText())

        self.win._append_log("INFO", "策略訊號：檢查進場")
        self.assertIn("策略訊號：檢查進場", self.win.event_log.toPlainText())
        self.assertIn("策略訊號：檢查進場", self.win.events_full_log.toPlainText())
        self.assertTrue(
            self._is_descendant(self.win.events_full_log, self.win._pages["events"])
        )

    def test_event_log_can_filter_strategy_related_entries(self):
        self.win._set_log_filter("all")
        self.win._append_log("INFO", "系統一般訊息")
        self.win._append_log("TRADE", "[策略觸發][BUY][2330 台積電] 策略=F1")

        self.assertIn("系統一般訊息", self.win.event_log.toPlainText())
        self.assertIn("策略=F1", self.win.events_full_log.toPlainText())

        self.win._set_log_filter("strategy")

        self.assertNotIn("系統一般訊息", self.win.event_log.toPlainText())
        self.assertIn("策略=F1", self.win.event_log.toPlainText())
        self.assertIn("策略=F1", self.win.events_full_log.toPlainText())

        self.win._append_log("INFO", "策略啟動準備中")
        self.assertIn("策略啟動準備中", self.win.event_log.toPlainText())

        self.win._set_log_filter("all")

        self.assertIn("系統一般訊息", self.win.event_log.toPlainText())
        self.assertIn("策略啟動準備中", self.win.events_full_log.toPlainText())

    def test_limitup_test_tab_renders_analysis_and_can_apply_mode(self):
        summary = [{
            "code": "2330",
            "name": "台積電",
            "market": "TSE",
            "candle": 1,
            "qty": 0,
            "pending": False,
            "vol_1s": 12,
            "blocked": False,
            "price": 1100.0,
            "limit_up": 1100.0,
            "prev_close": 1000.0,
            "change": 100.0,
            "change_pct": 10.0,
            "ask_qty": 0,
            "is_at_limit_up": True,
            "limit_up_mode": "strict_lock_with_effective_bid_tick_confirmed",
            "ask0_price": None,
            "ask0_volume": 0,
            "bid0_price": 1100.0,
            "bid0_volume": 88,
            "trade_bid": 1100.0,
            "trade_ask": 1100.0,
            "has_ask_levels": False,
            "has_bid_levels": True,
            "limit_up_signals": {
                "bid_at_limit": True,
                "last_at_limit": True,
                "ask_empty": True,
                "ask_qty_zero": True,
                "bid_qty_positive": True,
            },
            "limit_up_candidates": {
                "ask_or_bid_or_last": True,
                "ask_only": False,
                "bid_only": True,
                "bid_or_trade_flag": True,
                "bid_and_last": True,
                "bid_and_no_ask": True,
                "bid_and_zero_ask": True,
                "strict_lock_from_user_rule": True,
                "strict_lock_with_effective_bid": True,
                "strict_lock_with_effective_bid_tick_confirmed": True,
                "trade_price_only": True,
                "trade_flag_only": False,
            },
        }]

        class FakeEngine:
            def __init__(self):
                self.config = SimpleNamespace(limit_up_detection_mode="strict_lock_with_effective_bid_tick_confirmed")
                self.applied_modes = []

            def update_limit_up_mode(self, mode):
                self.applied_modes.append(mode)
                self.config.limit_up_detection_mode = mode
                return mode

        fake_engine = FakeEngine()
        self.win.engine = fake_engine
        self.win._running = True

        self.win._refresh_limitup_test_page(summary)

        self.assertEqual(self.win.limitup_test_stock_table.rowCount(), 1)
        self.assertGreaterEqual(
            self.win.limitup_test_mode_table.rowCount(),
            len(gui.LIMIT_UP_DETECTION_MODES),
        )
        self.assertIn("strict_lock_with_effective_bid_tick_confirmed", self.win.limitup_test_selected_lbl.text())
        self.assertIn("signals=", self.win.limitup_test_snapshot.toPlainText())

        for row in range(self.win.limitup_test_mode_table.rowCount()):
            item = self.win.limitup_test_mode_table.item(row, 0)
            if item and item.text() == "bid_only":
                self.win.limitup_test_mode_table.setCurrentCell(row, 0)
                break

        self.win._apply_selected_limitup_test_mode()

        combo = self.win._combos["limit_up_detection_mode"]
        self.assertFalse(combo.isEnabled())
        self.assertEqual(combo.currentData(), "strict_lock_with_effective_bid_tick_confirmed")
        self.assertEqual(self.win.cfg.limit_up_detection_mode, "strict_lock_with_effective_bid_tick_confirmed")
        self.assertEqual(fake_engine.applied_modes, ["strict_lock_with_effective_bid_tick_confirmed"])

    def test_monitor_count_action_text_and_column_autosize(self):
        summary = [
            {
                "code": "2330",
                "name": "台積電超長名稱測試股份有限公司",
                "market": "TSE",
                "candle": 1,
                "qty": 0,
                "pending": False,
                "vol_1s": 12,
                "blocked": False,
                "price": 88.5,
                "limit_up": 99.0,
                "prev_close": 90.0,
                "change": -1.5,
                "change_pct": -1.67,
                "ask_qty": 10,
                "is_at_limit_up": True,
            },
            {
                "code": "2317",
                "name": "鴻海",
                "market": "TSE",
                "candle": 2,
                "qty": 1,
                "pending": False,
                "vol_1s": 8,
                "blocked": False,
                "price": 120.0,
                "limit_up": 121.0,
                "prev_close": 110.0,
                "change": 10.0,
                "change_pct": 9.09,
                "ask_qty": 0,
                "is_at_limit_up": False,
            },
        ]

        self.win._render_monitor(summary)

        self.assertEqual(self.win.monitor_count_lbl.text(), "共 2 檔")
        self.assertEqual(self.win.monitor_table.item(0, 9).text(), "檢查進場")
        self.assertEqual(self.win.monitor_table.item(1, 9).text(), "監控出場")
        self.assertGreater(self.win.monitor_table.columnWidth(1), 70)

    def test_monitor_shows_blocked_reason_and_sell_pending_action(self):
        summary = [
            {
                "code": "2330",
                "name": "台積電",
                "market": "TSE",
                "candle": 1,
                "qty": 0,
                "pending": False,
                "vol_1s": 0,
                "blocked": True,
                "blocked_reason": "資金不足",
                "price": 1100.0,
                "limit_up": 1100.0,
                "prev_close": 1000.0,
                "change": 100.0,
                "change_pct": 10.0,
                "ask_qty": 0,
                "is_at_limit_up": True,
            },
            {
                "code": "2603",
                "name": "長榮",
                "market": "TSE",
                "candle": 1,
                "qty": 1,
                "pending": True,
                "vol_1s": 0,
                "blocked": False,
                "price": 210.0,
                "limit_up": 210.0,
                "prev_close": 191.0,
                "change": 19.0,
                "change_pct": 9.95,
                "ask_qty": 0,
                "is_at_limit_up": False,
            },
        ]

        self.win._render_monitor(summary)

        self.assertEqual(self.win.monitor_table.item(0, 8).text(), "出場中")
        self.assertEqual(self.win.monitor_table.item(0, 9).text(), "等待賣出")
        self.assertEqual(self.win.monitor_table.item(1, 8).text(), "資金不足")
        self.assertEqual(self.win.monitor_table.item(1, 9).text(), "不購買")

    def test_after_close_monitor_shows_close_status(self):
        self.win._is_after_market_close = lambda: True
        self.win._render_monitor([{
            "code": "1111",
            "name": "甲",
            "market": "TSE",
            "candle": 0,
            "qty": 0,
            "pending": False,
            "vol_1s": 0,
            "blocked": False,
            "price": 110.0,
            "limit_up": 121.0,
            "prev_close": 100.0,
            "change": 10.0,
            "change_pct": 10.0,
            "ask_qty": 0,
            "is_at_limit_up": False,
            "after_close_preview": True,
            "closed_at_limit_up": True,
        }])

        self.assertEqual(self.win.monitor_count_lbl.text(), "收盤檢視 1 檔")
        self.assertEqual(self.win.monitor_table.item(0, 8).text(), "收盤漲停")
        self.assertEqual(self.win.monitor_table.item(0, 9).text(), "明日觀察")

    def test_weekend_is_treated_as_after_market_close(self):
        sunday_morning = gui.datetime(2026, 5, 10, 9, 57)
        monday_morning = gui.datetime(2026, 5, 11, 9, 57)
        monday_close = gui.datetime(2026, 5, 11, 13, 30)

        self.assertTrue(self.win._is_after_market_close(sunday_morning))
        self.assertFalse(self.win._is_after_market_close(monday_morning))
        self.assertTrue(self.win._is_after_market_close(monday_close))

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

        with mock.patch("broker.universe.PreviousTradingDaysApiClient", side_effect=RuntimeError("api off")):
            summary = self.win._load_dashboard_preview_summary(
                broker, self.win._collect_config())

        self.assertEqual([item["code"] for item in summary], ["2330"])
        self.assertEqual(summary[0]["price"], 88.5)
        self.assertEqual(snapshot.calls[0], {"market": "TSE", "type": "COMMONSTOCK"})

    def test_after_close_preview_shows_next_day_f7_exclusions(self):
        class FakeSnapshot:
            def quotes(self, **_kwargs):
                return {"data": [
                    {
                        "symbol": "1111",
                        "name": "甲",
                        "previousClose": "100",
                        "closePrice": "110",
                        "tradeVolume": "2000",
                    },
                    {
                        "symbol": "2222",
                        "name": "乙",
                        "previousClose": "100",
                        "closePrice": "105",
                        "tradeVolume": "2000",
                    },
                ]}

        class FakeSdk:
            def __init__(self):
                self.marketdata = SimpleNamespace(
                    rest_client=SimpleNamespace(
                        stock=SimpleNamespace(snapshot=FakeSnapshot())
                    )
                )

            def init_realtime(self):
                return None

        broker = SimpleNamespace(_sdk=FakeSdk(), sdk=FakeSdk())
        self.win._is_after_market_close = lambda: True
        self.win._checks["market_twse"].setChecked(True)
        self.win._checks["market_tpex"].setChecked(False)
        self.win._checks["candle_k1"].setChecked(True)
        self.win._checks["candle_k2"].setChecked(False)
        self.win._fields["price_min"].setText("10")
        self.win._fields["price_max"].setText("500")
        self.win._fields["daily_volume_min"].setText("1")

        with mock.patch("broker.universe.PreviousTradingDaysApiClient", side_effect=RuntimeError("api off")):
            summary = self.win._load_dashboard_preview_summary(
                broker, self.win._collect_config())
        self.win._render_monitor(summary)

        rows = {item["code"]: item for item in summary}
        self.assertTrue(rows["1111"]["next_day_excluded"])
        self.assertFalse(rows["2222"].get("next_day_excluded", False))
        self.assertEqual(self.win.monitor_count_lbl.text(), "收盤檢視 1 / 明日排除 1 檔")
        status_by_code = {
            self.win.monitor_table.item(row, 0).text(): self.win.monitor_table.item(row, 8).text()
            for row in range(self.win.monitor_table.rowCount())
        }
        action_by_code = {
            self.win.monitor_table.item(row, 0).text(): self.win.monitor_table.item(row, 9).text()
            for row in range(self.win.monitor_table.rowCount())
        }
        self.assertEqual(status_by_code["1111"], "明日排除")
        self.assertEqual(action_by_code["1111"], "隔日不追")
        self.assertEqual(status_by_code["2222"], "收盤觀察")
        self.assertEqual(action_by_code["2222"], "明日觀察")

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

        with mock.patch("broker.universe.PreviousTradingDaysApiClient", side_effect=RuntimeError("api off")):
            self.win._start_trading()

            self.assertTrue(snapshot.entered.wait(1.0))
        self.assertTrue(self.win._strategy_starting)
        self.assertFalse(self.win._running)
        self.assertIn("載入中", self.win.strategy_status_lbl.text())

        self.win._stop_trading()
        snapshot.release.set()
        self.assertFalse(self.win._strategy_starting)
        self.assertFalse(self.win._running)

    def test_after_close_strategy_toggle_only_refreshes_preview(self):
        class FakeBroker:
            def create_realtime_feed(self):
                raise AssertionError("after close should not create realtime feed")

        self.win.broker = FakeBroker()
        self.win._is_after_market_close = lambda: True
        self.win._checks["market_twse"].setChecked(True)
        self.win._checks["market_tpex"].setChecked(False)
        self.win._preload_called = False
        self.win._preload_dashboard_preview_async = lambda broker=None: setattr(
            self.win, "_preload_called", True)

        self.win._start_trading()

        self.assertFalse(self.win._running)
        self.assertFalse(self.win._strategy_starting)
        self.assertFalse(self.win._toggles["strategy_enabled"].value)
        self.assertTrue(self.win._preload_called)
        self.assertIn("收盤預覽", self.win.strategy_status_lbl.text())

    def test_after_close_strategy_start_uses_market_snapshot(self):
        class FakeSnapshot:
            def __init__(self):
                self.calls = []

            def quotes(self, **kwargs):
                self.calls.append(kwargs)
                if "symbols" in kwargs:
                    return {"data": [{
                        "symbol": "2330",
                        "name": "台積電",
                        "previousClose": "90",
                        "closePrice": "88.5",
                        "tradeVolume": "2000",
                        "isDisposition": "N",
                        "isAttention": "N",
                        "canDayTrade": "Y",
                    }]}
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

        with mock.patch("broker.universe.PreviousTradingDaysApiClient", side_effect=RuntimeError("api off")):
            symbol_infos, feed, reserve_pool = self.win._load_trading_runtime(
                self.win.broker, self.win._collect_config())

        self.assertIsNone(feed)
        self.assertEqual(reserve_pool, {})
        self.assertEqual(snapshot.calls[0], {"market": "TSE", "type": "COMMONSTOCK"})
        self.assertEqual(snapshot.calls[1], {"symbols": ["2330"]})
        self.assertEqual(list(symbol_infos.keys()), ["2330"])

    def test_strategy_start_prefers_previous_trading_days_api(self):
        from broker.universe import build_symbol_info

        class FakeSnapshot:
            def __init__(self):
                self.calls = []

            def quotes(self, **kwargs):
                self.calls.append(kwargs)
                if "symbols" not in kwargs:
                    raise AssertionError("market snapshot should not be called when previous-days API succeeds")
                return {"data": [{
                    "symbol": "2330",
                    "name": "台積電",
                    "previousClose": "100",
                    "closePrice": "100",
                    "tradeVolume": "2000",
                    "isDisposition": "N",
                    "isAttention": "N",
                    "canDayTrade": "Y",
                }]}

        class FakeSdk:
            def __init__(self):
                self.snapshot = FakeSnapshot()
                self.marketdata = SimpleNamespace(
                    rest_client=SimpleNamespace(
                        stock=SimpleNamespace(snapshot=self.snapshot)
                    )
                )

            def init_realtime(self):
                return None

        class FakeBroker:
            def __init__(self):
                self._sdk = FakeSdk()
                self.sdk = self._sdk

            def create_realtime_feed(self):
                return None

        class FakePreviousDaysClient:
            instances = []

            def __init__(self):
                self.last_from_cache = True
                self.last_as_of = "2026-05-10"
                self.markets = None
                FakePreviousDaysClient.instances.append(self)

            def load_symbol_infos(self, markets):
                self.markets = tuple(markets)
                return {
                    "2330": build_symbol_info(
                        "2330", "台積電", "TSE", Decimal("100"),
                        quote_price=Decimal("100"), prev_volume=2000,
                        prior_limit_up_streak=0,
                    )
                }

        self.win._checks["market_twse"].setChecked(True)
        self.win._checks["market_tpex"].setChecked(False)
        self.win._fields["daily_volume_min"].setText("1")
        self.win._confirm_fubon_special_candidates = lambda loader, candidates, cfg: candidates

        with mock.patch("broker.universe.PreviousTradingDaysApiClient", FakePreviousDaysClient):
            symbol_infos, feed, reserve_pool = self.win._load_trading_runtime(
                FakeBroker(), self.win._collect_config())

        self.assertIsNone(feed)
        self.assertEqual(reserve_pool, {})
        self.assertEqual(FakePreviousDaysClient.instances[0].markets, ("TSE",))
        self.assertEqual(symbol_infos["2330"].is_attention, False)
        self.assertEqual(list(symbol_infos.keys()), ["2330"])

    def test_runtime_does_not_build_reserve_pool_below_symbol_limit(self):
        from broker.universe import build_symbol_info

        class FakeBroker:
            def __init__(self):
                self._sdk = object()

            def create_realtime_feed(self):
                return None

        class FakePreviousDaysClient:
            def __init__(self):
                self.last_from_cache = True
                self.last_as_of = "2026-05-10"

            def load_symbol_infos(self, markets):
                return {
                    f"{1000 + i}": build_symbol_info(
                        f"{1000 + i}",
                        f"股票{i}",
                        "TSE",
                        Decimal("50"),
                        quote_price=Decimal("50"),
                        prev_volume=10_000 - i,
                        prior_limit_up_streak=0,
                    )
                    for i in range(430)
                }

        self.win._checks["market_twse"].setChecked(True)
        self.win._checks["market_tpex"].setChecked(False)
        self.win._fields["daily_volume_min"].setText("1")
        self.win._confirm_fubon_special_candidates = lambda loader, candidates, cfg: candidates

        with mock.patch("broker.universe.PreviousTradingDaysApiClient", FakePreviousDaysClient):
            symbol_infos, feed, reserve_pool = self.win._load_trading_runtime(
                FakeBroker(), self.win._collect_config())

        self.assertIsNone(feed)
        self.assertEqual(len(symbol_infos), 430)
        self.assertEqual(reserve_pool, {})

    def test_runtime_builds_reserve_pool_only_for_overflow_candidates(self):
        from broker import FUBON_REALTIME_SYMBOL_LIMIT
        from broker.universe import build_symbol_info

        class FakeBroker:
            def __init__(self):
                self._sdk = object()

            def create_realtime_feed(self):
                return None

        class FakePreviousDaysClient:
            def __init__(self):
                self.last_from_cache = True
                self.last_as_of = "2026-05-10"

            def load_symbol_infos(self, markets):
                total = FUBON_REALTIME_SYMBOL_LIMIT + 3
                return {
                    f"{1000 + i}": build_symbol_info(
                        f"{1000 + i}",
                        f"股票{i}",
                        "TSE",
                        Decimal("50"),
                        quote_price=Decimal("50"),
                        prev_volume=20_000 - i,
                        prior_limit_up_streak=0,
                    )
                    for i in range(total)
                }

        self.win._checks["market_twse"].setChecked(True)
        self.win._checks["market_tpex"].setChecked(False)
        self.win._fields["daily_volume_min"].setText("1")
        self.win._confirm_fubon_special_candidates = lambda loader, candidates, cfg: candidates

        with mock.patch("broker.universe.PreviousTradingDaysApiClient", FakePreviousDaysClient):
            symbol_infos, feed, reserve_pool = self.win._load_trading_runtime(
                FakeBroker(), self.win._collect_config())

        self.assertIsNone(feed)
        self.assertEqual(len(symbol_infos), FUBON_REALTIME_SYMBOL_LIMIT)
        self.assertEqual(len(reserve_pool), 3)
        self.assertFalse(set(symbol_infos).intersection(reserve_pool))
        self.assertEqual(list(reserve_pool.keys()), ["1500", "1501", "1502"])


if __name__ == "__main__":
    unittest.main()
