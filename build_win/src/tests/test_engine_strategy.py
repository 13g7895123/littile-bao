"""
engine.TradingEngine strategy behavior tests.
"""
import os
import sys
import time
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker import BookEvent, TickEvent, build_symbol_info  # noqa: E402
from config import TradingConfig  # noqa: E402
from engine import TradingEngine  # noqa: E402


class TestTradingEngineStrategyRules(unittest.TestCase):
    def _make_engine(self, cfg: TradingConfig):
        logs = []
        trades = []
        strategy_events = []
        engine = TradingEngine(
            cfg,
            on_log=lambda level, msg: logs.append((level, msg)),
            on_trade=trades.append,
            on_status=lambda _summary: None,
            on_strategy_event=strategy_events.append,
        )
        return engine, logs, trades, strategy_events

    @staticmethod
    def _arm_entry_state(engine: TradingEngine, code: str = "2330"):
        state = engine._states[code]
        state.candle_index = 1
        state.limit_up_since = time.time()
        state.is_at_limit_up = True
        state.ask0_price = Decimal(str(state.info.limit_up))
        state.ask_qty_at_limit = 0
        state.last_1s_vol = 999
        return state

    def test_f4_sells_only_after_configured_open_ticks(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f5_enabled=False,
            f4_open_ticks_to_sell=2,
        )
        engine, logs, trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.position_qty = 1
        state.entry_price = Decimal("1100")
        state.touched_limit_up_today = True
        state.last_price = Decimal("1090")
        state.ask0_price = Decimal("1095")

        engine._tick(state, time.time())

        self.assertEqual(state.position_qty, 1)
        self.assertEqual(trades, [])

        state.ask0_price = Decimal("1090")
        engine._tick(state, time.time())

        self.assertEqual(state.position_qty, 0)
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertTrue(any("策略=F4" in msg for _level, msg in logs))
        self.assertEqual(strategy_events[-1]["strategy"], "F4")

    def test_f4_today_limitup_guard_blocks_overnight_position(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f5_enabled=False,
            f4_open_ticks_to_sell=1,
            f4_require_today_limitup=True,
        )
        engine, _logs, trades, _strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.position_qty = 1
        state.last_price = Decimal("1090")
        state.ask0_price = Decimal("1095")

        engine._tick(state, time.time())

        self.assertEqual(state.position_qty, 1)
        self.assertEqual(trades, [])

    def test_open_limitup_entry_toggle_blocks_entry(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f_open_limitup_entry_enabled=False,
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)
        state = engine._states["4919"]
        state.candle_index = 1
        state.limit_up_since = time.time()
        state.is_at_limit_up = True
        state.ask0_price = Decimal(str(state.info.limit_up))

        engine._tick(state, time.time())

        self.assertFalse(state.pending)

    def test_candle_index_uses_daily_prior_streak_once_per_day(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            candle_limit=2,
            per_stock_amount=2_000_000,
        )
        symbol_info = build_symbol_info(
            "1111", "測試股", "TSE", Decimal("100"),
            prev_volume=5000,
            prior_limit_up_streak=1,
        )
        logs = []
        engine = TradingEngine(
            cfg,
            symbol_infos={"1111": symbol_info},
            on_log=lambda level, msg: logs.append((level, msg)),
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
        )
        state = engine._states["1111"]

        engine._on_tick(TickEvent(
            code="1111",
            time=datetime(2026, 5, 18, 9, 1),
            price=Decimal("110"),
            volume=10,
        ))

        self.assertEqual(state.candle_index, 2)
        self.assertTrue(state.today_limit_up_counted)
        self.assertTrue(any("日K第 2 根" in msg for _level, msg in logs))

        state.last_price = Decimal("109")
        engine._on_book(BookEvent(
            code="1111",
            time=datetime(2026, 5, 18, 9, 2),
            ask=[],
            bid=[],
        ))
        self.assertIsNone(state.limit_up_since)

        engine._on_tick(TickEvent(
            code="1111",
            time=datetime(2026, 5, 18, 9, 3),
            price=Decimal("110"),
            volume=5,
        ))

        self.assertEqual(state.candle_index, 2)
        self.assertEqual(
            sum(1 for _level, msg in logs if "日K第 2 根" in msg),
            1,
        )

    def test_first_daily_limit_up_is_candle_one_without_prior_streak(self):
        cfg = TradingConfig(f1_enabled=False, f9_enabled=False, f10_enabled=False)
        symbol_info = build_symbol_info(
            "2222", "首根股", "TSE", Decimal("50"),
            prev_volume=5000,
            prior_limit_up_streak=0,
        )
        engine = TradingEngine(
            cfg,
            symbol_infos={"2222": symbol_info},
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
        )

        engine._on_tick(TickEvent(
            code="2222",
            time=datetime(2026, 5, 18, 9, 1),
            price=Decimal("55"),
            volume=10,
        ))

        self.assertEqual(engine._states["2222"].candle_index, 1)

    def test_default_limitup_mode_uses_last_price_as_fallback(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="ask_or_bid_or_last",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            price=Decimal("1100"),
            volume=10,
        ))

        self.assertTrue(engine._states["2330"].is_at_limit_up)

    def test_bid_and_no_ask_mode_requires_bid_lock_without_asks(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="bid_and_no_ask",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))

        self.assertTrue(engine._states["2330"].is_at_limit_up)

        engine2, _logs2, _trades2, _strategy_events2 = self._make_engine(cfg)
        engine2._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 2),
            ask=[SimpleNamespace(price=Decimal("1100"), volume=1)],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))

        self.assertFalse(engine2._states["2330"].is_at_limit_up)

    def test_consume_entry_skips_f1_when_mutex_enabled(self):
        cfg = TradingConfig(
            entry_before_time="00:00",
            ask_queue_threshold=1,
            f9_enabled=False,
            f10_enabled=False,
            f_consume_enabled=True,
            consume_qty_threshold=10,
            consume_mutex_with_f1=True,
            per_stock_amount=2_000_000,
        )
        engine, logs, _trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.candle_index = 1
        state.limit_up_since = time.time()
        state.is_at_limit_up = True
        state.ask0_price = Decimal(str(state.info.limit_up))
        state.ask_qty_at_limit = 999
        state.limit_up_consumed_qty = 10

        engine._tick(state, time.time())

        self.assertTrue(state.pending)
        self.assertTrue(any("策略=消化量+F7" in msg for _level, msg in logs))
        self.assertEqual(strategy_events[-1]["strategy"], "消化量+F7")
        self.assertEqual(strategy_events[-1]["code"], "2330")

    def test_per_stock_amount_below_one_lot_blocks_entry(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            per_stock_amount=100_000,
        )
        engine, logs, _trades, strategy_events = self._make_engine(cfg)
        state = self._arm_entry_state(engine, "2330")

        engine._tick(state, time.time())

        self.assertFalse(state.pending)
        self.assertTrue(state.entry_blocked)
        self.assertEqual(state.entry_blocked_reason, "資金不足")
        self.assertEqual(strategy_events, [])
        self.assertTrue(any("不足買進 1 張" in msg for _level, msg in logs))

    def test_per_stock_amount_uses_floor_lots_without_forcing_one(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            per_stock_amount=350_000,
        )
        engine, _logs, _trades, strategy_events = self._make_engine(cfg)
        state = self._arm_entry_state(engine, "3711")

        engine._tick(state, time.time())

        self.assertTrue(state.pending)
        self.assertEqual(strategy_events[-1]["details"]["qty"], "2")

    def test_buying_power_is_confirmed_before_order(self):
        class FakeAccountService:
            def snapshot(self):
                return SimpleNamespace(buying_power=Decimal("500000"))

        class FakeBroker:
            def __init__(self):
                self.orders = []

            def account_service(self):
                return FakeAccountService()

            def place_order(self, req):
                self.orders.append(req)
                return "O1"

        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            per_stock_amount=2_000_000,
            order_dry_run=False,
        )
        broker = FakeBroker()
        logs = []
        engine = TradingEngine(
            cfg,
            on_log=lambda level, msg: logs.append((level, msg)),
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            broker=broker,
        )
        state = self._arm_entry_state(engine, "2330")

        engine._tick(state, time.time())

        self.assertFalse(state.pending)
        self.assertEqual(state.entry_blocked_reason, "資金不足")
        self.assertEqual(broker.orders, [])
        self.assertTrue(any("可用額度" in msg for _level, msg in logs))

    def test_dry_run_bypasses_broker_buying_power_check(self):
        """模擬下單模式下，券商 buying_power 回傳 0 也不應擋進場。"""
        class FakeAccountService:
            def snapshot(self):
                # 模擬 SDK 尚未回覆或 API 失敗，buying_power = 0
                return SimpleNamespace(buying_power=Decimal("0"))

        class FakeBroker:
            def __init__(self):
                self.orders = []

            def account_service(self):
                return FakeAccountService()

            def place_order(self, req):
                self.orders.append(req)
                return "O1"

        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f11_enabled=False,
            per_stock_amount=2_000_000,
            order_dry_run=True,
        )
        broker = FakeBroker()
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            broker=broker,
        )
        state = self._arm_entry_state(engine, "2330")

        engine._tick(state, time.time())

        # 模擬下單時應略過 buying_power 比對 → 進入 pending
        self.assertTrue(state.pending)
        self.assertEqual(state.entry_blocked_reason, "")

    def test_skip_reason_records_filter_failures(self):
        """進場條件未通過時，state.last_skip_reason 應記錄原因（供 GUI 顯示）。"""
        cfg = TradingConfig(
            f1_enabled=True,
            entry_before_time="00:00",  # 立刻過時，必擋下
            f9_enabled=False,
            f10_enabled=False,
        )
        engine, _logs, _trades, _events = self._make_engine(cfg)
        state = self._arm_entry_state(engine, "2330")

        engine._tick(state, time.time())

        self.assertFalse(state.pending)
        self.assertIn("F1", state.last_skip_reason)
        self.assertIn("進場時段", state.last_skip_reason)

    def test_f11_special_status_is_confirmed_before_order(self):
        class FakeAccountService:
            def snapshot(self):
                return SimpleNamespace(buying_power=Decimal("3000000"))

        class FakeBroker:
            def __init__(self):
                self.load_calls = []
                self.orders = []

            def account_service(self):
                return FakeAccountService()

            def load_symbol_info(self, codes):
                self.load_calls.append(list(codes))
                return {
                    "2330": SimpleNamespace(
                        is_disposal=False,
                        is_attention=True,
                        is_day_trade_restricted=False,
                    )
                }

            def place_order(self, req):
                self.orders.append(req)
                return "O1"

        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            per_stock_amount=2_000_000,
        )
        broker = FakeBroker()
        logs = []
        engine = TradingEngine(
            cfg,
            on_log=lambda level, msg: logs.append((level, msg)),
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            broker=broker,
        )
        state = self._arm_entry_state(engine, "2330")

        engine._tick(state, time.time())

        self.assertEqual(broker.load_calls, [["2330"]])
        self.assertEqual(broker.orders, [])
        self.assertEqual(state.entry_blocked_reason, "特殊股排除")
        self.assertTrue(any("注意股" in msg for _level, msg in logs))

    def test_sell_all_strategy_positions_sells_current_positions(self):
        cfg = TradingConfig(f9_enabled=False, f5_enabled=False)
        engine, logs, trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.position_qty = 1
        state.entry_price = Decimal("1100")
        state.last_price = Decimal("1090")

        sold = engine.sell_all_strategy_positions("unit-test")

        self.assertEqual(sold, 1)
        self.assertEqual(state.position_qty, 0)
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertTrue(any("策略=MANUAL_ALL" in msg for _level, msg in logs))
        self.assertEqual(strategy_events[-1]["strategy"], "MANUAL_ALL")

    def test_empty_symbol_infos_does_not_fallback_to_mock_stocks(self):
        cfg = TradingConfig()
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            symbol_infos={},
        )

        self.assertEqual(engine._states, {})


if __name__ == "__main__":
    unittest.main()
