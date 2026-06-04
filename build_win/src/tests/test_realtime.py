"""
realtime + engine 整合測試（不依賴真實 fubon_neo SDK）。
"""
import os
import sys
import threading
import time
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker import (  # noqa: E402
    BookEvent,
    BookLevel,
    MockRealtimeFeed,
    SymbolMeta,
    TickEvent,
)
from broker.realtime import (  # noqa: E402
    FUBON_REALTIME_MAX_CONNECTIONS,
    FUBON_REALTIME_SUBSCRIPTION_LIMIT_PER_CONNECTION,
    FUBON_REALTIME_SYMBOL_LIMIT,
    FubonRealtimeFeed,
)
from broker.errors import FubonNotLoggedInError  # noqa: E402


class _FakeStockWebSocket:
    def __init__(self) -> None:
        self.handlers: dict = {}
        self.subscribe_calls: list = []
        self.connected = False
        self.disconnected = False

    def on(self, event, callback) -> None:
        self.handlers[event] = callback

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def subscribe(self, payload) -> None:
        self.subscribe_calls.append(payload)


class TestMockRealtimeFeed(unittest.TestCase):
    def test_emits_tick_and_book(self):
        feed = MockRealtimeFeed(tick_interval=0.05, book_interval=0.1)
        ticks: list = []
        books: list = []
        ev = threading.Event()

        def on_tick(t):
            ticks.append(t)
            if len(ticks) >= 3 and len(books) >= 1:
                ev.set()

        def on_book(b):
            books.append(b)
            if len(ticks) >= 3 and len(books) >= 1:
                ev.set()

        feed.on_tick(on_tick)
        feed.on_book(on_book)
        feed.subscribe(["2330"], {
            "2330": SymbolMeta(
                code="2330",
                limit_up=Decimal("1100"),
                prev_close=Decimal("1000"),
            ),
        })
        feed.start()
        try:
            self.assertTrue(ev.wait(2.0), "未在時限內收到事件")
        finally:
            feed.stop()

        self.assertGreater(len(ticks), 0)
        self.assertGreater(len(books), 0)
        self.assertEqual(ticks[0].code, "2330")


class TestEngineWithMockFeed(unittest.TestCase):
    def test_engine_consumes_feed(self):
        from config import TradingConfig
        from engine import TradingEngine

        cfg = TradingConfig()
        logs: list = []
        feed = MockRealtimeFeed(tick_interval=0.05, book_interval=0.1)
        eng = TradingEngine(
            config=cfg,
            on_log=lambda lvl, msg: logs.append((lvl, msg)),
            on_trade=lambda d: None,
            on_status=lambda _s: None,
            feed=feed,
        )
        eng.start()
        try:
            time.sleep(1.5)
            summary = eng.get_summary()
            self.assertGreater(len(summary), 0)
            # 1 秒成交量應由真實 tick 累計（非 random.randint(10,850) 區間驗證困難，
            # 但至少必須 >0 表示 tick 有進到 engine）
            any_vol = any(s["vol_1s"] > 0 for s in summary)
            self.assertTrue(any_vol, "engine 未收到任何 tick")
        finally:
            eng.stop()


class TestFubonRealtimeFeedSkeleton(unittest.TestCase):
    def test_to_tick_prefers_api_time_and_keeps_recv_time(self):
        payload = {
            "symbol": "2330",
            "price": 1100,
            "size": 5,
            "volume": 100,
            "time": 1779762837138002,
            "isLimitUpPrice": True,
        }

        tick = FubonRealtimeFeed._to_tick(payload)

        self.assertEqual(tick.code, "2330")
        self.assertEqual(tick.time, tick.api_time)
        self.assertIsNotNone(tick.api_time)
        self.assertIsNotNone(tick.recv_time)
        self.assertLess(tick.api_time, tick.recv_time)
        self.assertEqual(tick.api_time, datetime.fromtimestamp(1779762837.138002))
        self.assertTrue(tick.is_limit_up_price)

    def test_to_book_prefers_api_time_and_keeps_recv_time(self):
        payload = {
            "symbol": "2330",
            "time": 1779762837138002,
            "asks": [{"price": 1100, "size": 0}],
            "bids": [{"price": 1100, "size": 99}],
        }

        book = FubonRealtimeFeed._to_book(payload)

        self.assertEqual(book.code, "2330")
        self.assertEqual(book.time, book.api_time)
        self.assertIsNotNone(book.api_time)
        self.assertIsNotNone(book.recv_time)
        self.assertLess(book.api_time, book.recv_time)
        self.assertEqual(book.api_time, datetime.fromtimestamp(1779762837.138002))
        self.assertEqual(book.bid[0].volume, 99)

    def test_subscribe_caps_symbols_to_five_connection_limit(self):
        feed = FubonRealtimeFeed(SimpleNamespace())
        codes = [f"{i:04d}" for i in range(FUBON_REALTIME_SYMBOL_LIMIT + 25)]

        feed.subscribe(codes, {})

        self.assertEqual(len(feed._subscribed), FUBON_REALTIME_SYMBOL_LIMIT)
        self.assertEqual(feed._subscribed[0], "0000")
        self.assertEqual(feed._subscribed[-1], f"{FUBON_REALTIME_SYMBOL_LIMIT - 1:04d}")

    def test_101_symbols_use_two_connections_for_trades_and_books(self):
        clients: list[_FakeStockWebSocket] = []

        def factory(_adapter, _mode, _index):
            client = _FakeStockWebSocket()
            clients.append(client)
            return client

        feed = FubonRealtimeFeed(SimpleNamespace(sdk=SimpleNamespace()), ws_client_factory=factory)
        feed.subscribe([f"{i:04d}" for i in range(101)], {})

        feed.start()
        try:
            self.assertEqual(len(clients), 2)
            self.assertEqual(len(clients[0].subscribe_calls[0]["symbols"]), 100)
            self.assertEqual(len(clients[1].subscribe_calls[0]["symbols"]), 1)
            for client in clients:
                self.assertTrue(client.connected)
                self.assertEqual([c["channel"] for c in client.subscribe_calls], ["trades", "books"])
        finally:
            feed.stop()
        self.assertTrue(all(client.disconnected for client in clients))

    def test_500_symbols_use_five_connections_without_exceeding_quota(self):
        clients: list[_FakeStockWebSocket] = []

        def factory(_adapter, _mode, _index):
            client = _FakeStockWebSocket()
            clients.append(client)
            return client

        feed = FubonRealtimeFeed(SimpleNamespace(sdk=SimpleNamespace()), ws_client_factory=factory)
        feed.subscribe([f"{i:04d}" for i in range(FUBON_REALTIME_SYMBOL_LIMIT)], {})

        feed.start()
        try:
            self.assertEqual(len(clients), FUBON_REALTIME_MAX_CONNECTIONS)
            for client in clients:
                self.assertTrue(client.connected)
                self.assertEqual([c["channel"] for c in client.subscribe_calls], ["trades", "books"])
                subscription_count = sum(len(c["symbols"]) for c in client.subscribe_calls)
                self.assertLessEqual(
                    subscription_count,
                    FUBON_REALTIME_SUBSCRIPTION_LIMIT_PER_CONNECTION,
                )
            self.assertEqual(len(clients[0].subscribe_calls[0]["symbols"]), 100)
            self.assertEqual(clients[-1].subscribe_calls[-1]["symbols"][-1], "0499")
        finally:
            feed.stop()

    def test_start_without_login_raises(self):
        from broker import FubonAdapter
        adapter = FubonAdapter(
            personal_id="A1",
            password="x",
            cert_path="/tmp/none.pfx",
            cert_password="x",
            branch_no="6460",
            account_no="1234567",
        )
        feed = FubonRealtimeFeed(adapter)
        with self.assertRaises(FubonNotLoggedInError):
            feed.start()

    def test_disconnect_event_notifies_callback(self):
        clients: list[_FakeStockWebSocket] = []
        events: list[str] = []

        def factory(_adapter, _mode, _index):
            client = _FakeStockWebSocket()
            clients.append(client)
            return client

        feed = FubonRealtimeFeed(SimpleNamespace(sdk=SimpleNamespace()), ws_client_factory=factory)
        feed.set_disconnect_callback(events.append)
        feed.subscribe(["2330"], {})

        feed.start()
        try:
            clients[0].handlers["disconnect"]("socket closed")
        finally:
            feed.stop()

        self.assertEqual(len(events), 1)
        self.assertIn("websocket #1 disconnected", events[0])

    def test_manual_stop_does_not_notify_disconnect_callback(self):
        clients: list[_FakeStockWebSocket] = []
        events: list[str] = []

        def factory(_adapter, _mode, _index):
            client = _FakeStockWebSocket()
            clients.append(client)
            return client

        feed = FubonRealtimeFeed(SimpleNamespace(sdk=SimpleNamespace()), ws_client_factory=factory)
        feed.set_disconnect_callback(events.append)
        feed.subscribe(["2330"], {})

        feed.start()
        feed.stop()
        clients[0].handlers["disconnect"]("manual close")

        self.assertEqual(events, [])

    def test_error_event_with_timeout_notifies_disconnect_callback(self):
        clients: list[_FakeStockWebSocket] = []
        events: list[str] = []

        def factory(_adapter, _mode, _index):
            client = _FakeStockWebSocket()
            clients.append(client)
            return client

        feed = FubonRealtimeFeed(SimpleNamespace(sdk=SimpleNamespace()), ws_client_factory=factory)
        feed.set_disconnect_callback(events.append)
        feed.subscribe(["2330"], {})

        feed.start()
        try:
            clients[0].handlers["error"](RuntimeError("Connection timed out"))
        finally:
            feed.stop()

        self.assertEqual(len(events), 1)
        self.assertIn("websocket #1 error", events[0])

    def test_disconnect_notification_only_fires_once_per_start(self):
        clients: list[_FakeStockWebSocket] = []
        events: list[str] = []

        def factory(_adapter, _mode, _index):
            client = _FakeStockWebSocket()
            clients.append(client)
            return client

        feed = FubonRealtimeFeed(SimpleNamespace(sdk=SimpleNamespace()), ws_client_factory=factory)
        feed.set_disconnect_callback(events.append)
        feed.subscribe(["2330"], {})

        feed.start()
        try:
            clients[0].handlers["error"](RuntimeError("Connection timed out"))
            clients[0].handlers["disconnect"]("socket closed")
        finally:
            feed.stop()

        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
