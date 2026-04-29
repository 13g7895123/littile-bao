"""
realtime + engine 整合測試（不依賴真實 fubon_neo SDK）。
"""
import os
import sys
import threading
import time
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker import (  # noqa: E402
    BookEvent,
    BookLevel,
    MockRealtimeFeed,
    SymbolMeta,
    TickEvent,
)
from broker.realtime import FubonRealtimeFeed  # noqa: E402
from broker.errors import FubonNotLoggedInError  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
