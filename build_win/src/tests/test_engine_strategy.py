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

from broker import BookEvent, FillEvent, OrderEvent, OrderSide, OrderStatus, TickEvent, build_symbol_info  # noqa: E402
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

    @staticmethod
    def _arm_exit_state(engine: TradingEngine, code: str = "2330"):
        state = engine._states[code]
        state.position_qty = 1
        state.entry_price = Decimal(str(state.info.limit_up))
        state.candle_index = 1
        state.touched_limit_up_today = True
        state.is_at_limit_up = True
        state.last_price = Decimal(str(state.info.limit_up))
        state.ask0_price = Decimal(str(state.info.limit_up))
        state.has_ask_levels = True
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
        self.assertIn("detail_time", trades[-1])
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

    def test_f4_treats_non_limit_state_without_ask_as_open_board(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f5_enabled=False,
            f4_open_ticks_to_sell=1,
            f4_require_today_limitup=True,
        )
        engine, logs, trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.position_qty = 1
        state.entry_price = Decimal("1100")
        state.touched_limit_up_today = True
        state.last_price = Decimal("1099")
        state.is_at_limit_up = False
        state.ask0_price = None

        engine._tick(state, time.time())

        self.assertEqual(state.position_qty, 0)
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertTrue(any("策略=F4" in msg for _level, msg in logs))
        self.assertEqual(strategy_events[-1]["strategy"], "F4")

    def test_f4_ignores_market_event_that_triggered_buy_fill(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f5_enabled=False,
            f4_open_ticks_to_sell=1,
        )
        engine, _logs, trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        entry_event_time = datetime(2026, 6, 17, 9, 17, 4, 73000)
        state.pending = True
        state.pending_side = "BUY"
        state.pending_order_id = "B1"
        state.pending_entry_strategy = "PRELOCK_ASK"
        state.candle_index = 1
        state.touched_limit_up_today = True
        state.is_at_limit_up = False
        state.last_price = Decimal(str(state.info.limit_up))
        state.ask0_price = Decimal(str(state.info.limit_up))
        state.last_market_event_time = entry_event_time

        engine._on_broker_fill(FillEvent(
            order_id="B1",
            code="2330",
            name="台積電",
            side=OrderSide.BUY,
            price=Decimal(str(state.info.limit_up)),
            qty=1,
            time=datetime(2026, 6, 17, 9, 17, 5, 718000),
        ))

        engine._tick(state, entry_event_time.timestamp() + 2)

        self.assertEqual(state.position_qty, 1)
        self.assertEqual([t["action"] for t in trades], ["BUY"])
        self.assertFalse(any(ev["side"] == "SELL" for ev in strategy_events))

        state.last_market_event_time = datetime(2026, 6, 17, 9, 17, 6)
        engine._tick(state, entry_event_time.timestamp() + 3)

        self.assertEqual(state.position_qty, 1)
        self.assertEqual([t["action"] for t in trades], ["BUY"])

        state.prelock_relocked_after_entry = True
        state.last_market_event_time = datetime(2026, 6, 17, 9, 17, 7)
        engine._tick(state, entry_event_time.timestamp() + 4)

        self.assertEqual(state.position_qty, 0)
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertEqual(strategy_events[-1]["strategy"], "F4")

    def test_f5_threshold_is_inclusive_at_499(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_enabled=False,
            volume_spike_sell_threshold=499,
        )
        engine, logs, trades, strategy_events = self._make_engine(cfg)
        state = self._arm_exit_state(engine)
        now = time.time()
        state.tick_vols.append((now, 499))

        engine._tick(state, now)

        self.assertEqual(state.position_qty, 0)
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertIn(">= 499", trades[-1]["note"])
        self.assertTrue(any("策略=F5" in msg for _level, msg in logs))
        self.assertEqual(strategy_events[-1]["strategy"], "F5")

    def test_sell_prefers_f5_when_spike_occurs_before_open_board(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_open_ticks_to_sell=1,
            volume_spike_sell_threshold=499,
        )
        engine, _logs, trades, strategy_events = self._make_engine(cfg)
        state = self._arm_exit_state(engine)

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 6, 3, 9, 46, 32, 118332),
            price=Decimal("1100"),
            volume=499,
        ))
        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 6, 3, 9, 46, 32, 148789),
            ask=[SimpleNamespace(price=Decimal("1095"), volume=10)],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=50)],
        ))

        engine._tick(state, time.time())

        self.assertEqual(strategy_events[-1]["strategy"], "F5")
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertIn(">= 499", trades[-1]["note"])
        self.assertEqual(strategy_events[-1]["details"]["winner_strategy"], "F5")

    def test_sell_prefers_f4_when_open_board_occurs_before_spike(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_open_ticks_to_sell=1,
            volume_spike_sell_threshold=499,
        )
        engine, _logs, trades, strategy_events = self._make_engine(cfg)
        state = self._arm_exit_state(engine)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 6, 3, 9, 46, 32, 118332),
            ask=[SimpleNamespace(price=Decimal("1095"), volume=10)],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=50)],
        ))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 6, 3, 9, 46, 32, 148789),
            price=Decimal("1095"),
            volume=499,
        ))

        engine._tick(state, time.time())

        self.assertEqual(strategy_events[-1]["strategy"], "F4")
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertIn("漲停板打開", trades[-1]["note"])
        self.assertEqual(strategy_events[-1]["details"]["winner_strategy"], "F4")

    def test_sell_tie_break_prefers_f5_when_trigger_times_match(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_open_ticks_to_sell=1,
            volume_spike_sell_threshold=499,
        )
        engine, _logs, trades, strategy_events = self._make_engine(cfg)
        state = self._arm_exit_state(engine)
        same_ts = datetime(2026, 6, 3, 10, 0, 0).timestamp()
        state.is_at_limit_up = False
        state.ask0_price = Decimal("1095")
        state.last_1s_vol = 499

        engine._record_sell_trigger_candidates(state, same_ts)
        engine._tick(state, time.time())

        self.assertEqual(strategy_events[-1]["strategy"], "F5")
        self.assertEqual(trades[-1]["action"], "SELL")

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

    def test_prelock_ask_entry_buys_before_limit_lock(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f11_enabled=False,
            f_prelock_ask_entry_enabled=True,
            per_stock_amount=2_000_000,
        )
        engine, logs, _trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.ask0_price = Decimal(str(state.info.limit_up))
        state.ask0_volume = 44
        state.ask_qty_at_limit = 44
        state.last_price = Decimal(str(state.info.limit_up))
        state.is_at_limit_up = False

        engine._tick(state, time.time())

        self.assertTrue(state.pending or state.position_qty > 0)
        if state.pending:
            self.assertEqual(state.pending_entry_strategy, "PRELOCK_ASK")
        else:
            self.assertTrue(state.entry_via_prelock_ask)
        self.assertEqual(strategy_events[-1]["strategy"], "鎖前委賣+F7")
        self.assertTrue(any("鎖板前漲停委賣 44 張 < 100 張" in msg for _level, msg in logs))

    def test_prelock_ask_entry_buys_when_limit_ask_disappears(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f11_enabled=False,
            f_prelock_ask_entry_enabled=True,
            per_stock_amount=2_000_000,
        )
        engine, logs, _trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.last_limit_ask0_price = Decimal(str(state.info.limit_up))
        state.last_limit_ask0_volume = 249
        state.ask0_price = None
        state.ask0_volume = 0
        state.ask_qty_at_limit = 0
        state.last_price = Decimal(str(state.info.limit_up))
        state.is_at_limit_up = False

        engine._tick(state, time.time())

        self.assertTrue(state.pending or state.position_qty > 0)
        if state.pending:
            self.assertEqual(state.pending_entry_strategy, "PRELOCK_ASK")
        else:
            self.assertTrue(state.entry_via_prelock_ask)
        self.assertEqual(strategy_events[-1]["strategy"], "鎖前委賣+F7")
        self.assertTrue(strategy_events[-1]["details"]["prelock_ask_disappeared"])
        self.assertEqual(strategy_events[-1]["details"]["previous_limit_ask_qty"], "249")
        self.assertTrue(any("鎖板前漲停委賣消失（前筆 249 張）" in msg for _level, msg in logs))

    def test_prelock_ask_entry_requires_best_ask_at_limit(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f_prelock_ask_entry_enabled=True,
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.ask0_price = Decimal(str(state.info.limit_up)) - Decimal("5")
        state.ask0_volume = 2
        state.ask_qty_at_limit = 0
        state.last_price = Decimal(str(state.info.limit_up))
        state.is_at_limit_up = False

        engine._tick(state, time.time())

        self.assertFalse(state.pending)
        self.assertEqual(state.position_qty, 0)

    def test_prelock_stop_sells_only_prelock_entry_after_configured_ticks(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_enabled=False,
            f5_enabled=False,
            f_prelock_stop_enabled=True,
            prelock_stop_ticks=2,
        )
        engine, _logs, trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.position_qty = 1
        state.entry_price = Decimal(str(state.info.limit_up))
        state.entry_via_prelock_ask = True
        state.last_price = state.entry_price - engine._tick_size(state.entry_price)

        engine._tick(state, time.time())

        self.assertEqual(state.position_qty, 1)
        self.assertEqual(trades, [])

        state.last_price = state.entry_price - engine._tick_size(state.entry_price) * Decimal("2")
        engine._tick(state, time.time())

        self.assertEqual(state.position_qty, 0)
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertIn("鎖板前委賣進場停損", trades[-1]["note"])
        self.assertEqual(strategy_events[-1]["strategy"], "鎖前停損")

    def test_prelock_stop_does_not_apply_to_regular_limit_lock_entry(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_enabled=False,
            f5_enabled=False,
            f_prelock_stop_enabled=True,
            prelock_stop_ticks=2,
        )
        engine, _logs, trades, _strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        state.position_qty = 1
        state.entry_price = Decimal(str(state.info.limit_up))
        state.entry_via_prelock_ask = False
        state.last_price = state.entry_price - engine._tick_size(state.entry_price) * Decimal("2")

        engine._tick(state, time.time())

        self.assertEqual(state.position_qty, 1)
        self.assertEqual(trades, [])

    def test_candle_index_uses_daily_prior_streak_once_per_day(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="ask_or_bid_or_last",
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

    def test_engine_detaches_broker_callbacks_on_stop(self):
        cfg = TradingConfig()
        broker = SimpleNamespace()
        fill_subs = []
        order_subs = []

        broker.on_filled = fill_subs.append
        broker.off_filled = lambda cb: fill_subs.remove(cb) if cb in fill_subs else None
        broker.on_order = order_subs.append
        broker.off_order = lambda cb: order_subs.remove(cb) if cb in order_subs else None

        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            broker=broker,
        )

        engine.start()
        self.assertEqual(fill_subs, [engine._on_broker_fill])
        self.assertEqual(order_subs, [engine._on_broker_order])

        engine.stop()
        self.assertEqual(fill_subs, [])
        self.assertEqual(order_subs, [])

        engine.start()
        self.assertEqual(fill_subs, [engine._on_broker_fill])
        self.assertEqual(order_subs, [engine._on_broker_order])

        engine.stop()
        self.assertEqual(fill_subs, [])
        self.assertEqual(order_subs, [])

    def test_first_daily_limit_up_is_candle_one_without_prior_streak(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="ask_or_bid_or_last",
        )
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
        self.assertFalse(any("LimitUpDiag" in msg for _level, msg in _logs))

    def test_startup_locked_limitup_is_marked_and_waits_for_relock(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            startup_limit_up_detection_mode="ask_or_bid_or_last",
            limit_up_detection_mode="ask_or_bid_or_last",
        )
        engine, logs, _trades, _strategy_events = self._make_engine(cfg)
        engine._started_at = datetime(2026, 5, 19, 9, 0, 0)
        state = engine._states["2330"]

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            price=Decimal("1100"),
            volume=10,
        ))

        self.assertTrue(state.startup_limitup_blocked)
        self.assertEqual(state.candle_index, 0)
        self.assertEqual(state.last_skip_reason, "程式啟用後已漲停")
        self.assertTrue(any("啟用時已鎖漲停" in msg for _level, msg in logs))

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 2),
            price=Decimal("1090"),
            volume=5,
        ))

        self.assertFalse(state.startup_limitup_blocked)
        self.assertFalse(state.is_at_limit_up)

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 3),
            price=Decimal("1100"),
            volume=8,
        ))

        self.assertEqual(state.candle_index, 1)
        self.assertTrue(state.is_at_limit_up)

    def test_startup_lock_mode_can_block_even_when_intraday_mode_is_strict(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            startup_limit_up_detection_mode="bid_or_trade_flag",
            limit_up_detection_mode="strict_lock_from_user_rule",
        )
        engine, logs, _trades, _strategy_events = self._make_engine(cfg)
        engine._started_at = datetime(2026, 5, 19, 9, 0, 0)
        state = engine._states["2330"]

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("0"), volume=999)],
        ))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 1),
            price=Decimal("1100"),
            volume=10,
            is_limit_up_price=True,
            is_limit_up_bid=True,
        ))

        self.assertTrue(state.startup_limitup_blocked)
        self.assertTrue(state.is_at_limit_up)
        self.assertFalse(state.touched_limit_up_today)
        self.assertEqual(state.candle_index, 0)
        self.assertFalse(state.limit_up_candidate_states["strict_lock_from_user_rule"])
        self.assertFalse(state.limit_up_candidate_states["strict_lock_with_effective_bid"])
        self.assertTrue(any("判斷=bid_or_trade_flag" in msg for _level, msg in logs))

    def test_startup_lock_mode_unblocks_after_old_lock_rule_breaks(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            startup_limit_up_detection_mode="bid_or_trade_flag",
            limit_up_detection_mode="strict_lock_from_user_rule",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)
        engine._started_at = datetime(2026, 5, 19, 9, 0, 0)
        state = engine._states["2330"]

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("0"), volume=999)],
        ))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 1),
            price=Decimal("1100"),
            volume=10,
            is_limit_up_price=True,
            is_limit_up_bid=True,
        ))
        self.assertTrue(state.startup_limitup_blocked)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 2),
            ask=[SimpleNamespace(price=Decimal("1100"), volume=1)],
            bid=[SimpleNamespace(price=Decimal("1095"), volume=20)],
        ))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 2, 1),
            price=Decimal("1095"),
            volume=5,
            is_limit_up_price=False,
            is_limit_up_bid=False,
        ))

        self.assertFalse(state.startup_limitup_blocked)
        self.assertFalse(state.is_at_limit_up)

    def test_f1_respects_start_time(self):
        cfg = TradingConfig(
            start_time="09:05",
            entry_before_time="10:00",
            f9_enabled=False,
            f10_enabled=False,
            per_stock_amount=2_000_000,
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)
        engine._current_datetime = lambda: datetime(2026, 5, 19, 9, 4, 59)
        state = self._arm_entry_state(engine)

        engine._tick(state, time.time())

        self.assertFalse(state.pending)
        self.assertEqual(state.last_skip_reason, "F1:未到開始時間 09:05")

    def test_f1_stops_at_market_close_even_if_configured_later(self):
        cfg = TradingConfig(
            start_time="09:00",
            entry_before_time="14:00",
            f9_enabled=False,
            f10_enabled=False,
            per_stock_amount=2_000_000,
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)
        engine._current_datetime = lambda: datetime(2026, 5, 19, 13, 30, 1)
        state = self._arm_entry_state(engine)

        engine._tick(state, time.time())

        self.assertFalse(state.pending)
        self.assertEqual(state.last_skip_reason, "F1:已過進場時段 13:30")

    def test_auto_sell_is_disabled_at_and_after_1325(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f5_enabled=False,
            f4_open_ticks_to_sell=1,
        )
        engine, _logs, trades, _strategy_events = self._make_engine(cfg)
        engine._running = True
        engine._current_datetime = lambda: datetime(2026, 5, 19, 13, 25, 0)
        state = engine._states["2330"]
        state.position_qty = 1
        state.entry_price = Decimal("1100")
        state.touched_limit_up_today = True
        state.last_price = Decimal("1095")
        state.ask0_price = Decimal("1095")
        state.is_at_limit_up = False

        engine._tick(state, time.time())

        self.assertEqual(state.position_qty, 1)
        self.assertEqual(trades, [])

    def test_auto_entry_is_disabled_at_and_after_1325(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            per_stock_amount=2_000_000,
        )
        engine, _logs, trades, _strategy_events = self._make_engine(cfg)
        engine._running = True
        engine._current_datetime = lambda: datetime(2026, 5, 19, 13, 25, 0)
        state = self._arm_entry_state(engine)

        engine._tick(state, time.time())

        self.assertFalse(state.pending)
        self.assertEqual(trades, [])
        self.assertEqual(state.last_skip_reason, "已過自動交易截止 13:25")

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

    def test_bid_and_zero_ask_mode_requires_bid_lock_and_zero_ask(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="bid_and_zero_ask",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            ask=[SimpleNamespace(price=Decimal("1100"), volume=3)],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))
        self.assertFalse(engine._states["2330"].is_at_limit_up)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 2),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))
        self.assertTrue(engine._states["2330"].is_at_limit_up)

    def test_strict_lock_from_user_rule_matches_requested_condition(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="strict_lock_from_user_rule",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            ask=[SimpleNamespace(price=Decimal("1100"), volume=3)],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 1),
            price=Decimal("1100"),
            volume=10,
            cum_volume=100,
            is_limit_up_price=True,
        ))
        self.assertFalse(engine._states["2330"].is_at_limit_up)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 2),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))
        self.assertTrue(engine._states["2330"].is_at_limit_up)

        engine2, _logs2, _trades2, _strategy_events2 = self._make_engine(cfg)
        engine2._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 3),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=0)],
        ))
        engine2._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 3, 1),
            price=Decimal("1100"),
            volume=10,
            cum_volume=100,
            is_limit_up_price=True,
        ))
        self.assertFalse(engine2._states["2330"].is_at_limit_up)

        engine3, _logs3, _trades3, _strategy_events3 = self._make_engine(cfg)
        engine3._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 4),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))
        engine3._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 4, 1),
            price=Decimal("1100"),
            volume=10,
            cum_volume=100,
            is_limit_up_price=False,
        ))
        self.assertFalse(engine3._states["2330"].is_at_limit_up)

    def test_strict_lock_with_effective_bid_skips_zero_placeholder_level(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="strict_lock_with_effective_bid",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            ask=[],
            bid=[
                SimpleNamespace(price=Decimal("0"), volume=999),
                SimpleNamespace(price=Decimal("1100"), volume=99),
            ],
        ))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 1),
            price=Decimal("1100"),
            volume=10,
            cum_volume=100,
            is_limit_up_price=True,
            is_limit_up_bid=False,
        ))

        self.assertTrue(engine._states["2330"].is_at_limit_up)
        self.assertFalse(engine._states["2330"].limit_up_candidate_states["strict_lock_from_user_rule"])
        self.assertTrue(engine._states["2330"].limit_up_candidate_states["strict_lock_with_effective_bid"])
        self.assertFalse(engine._states["2330"].limit_up_candidate_states["strict_lock_with_effective_bid_tick_confirmed"])

    def test_strict_lock_with_effective_bid_tick_confirmed_requires_trade_bid_flag(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="strict_lock_with_effective_bid_tick_confirmed",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            ask=[],
            bid=[
                SimpleNamespace(price=Decimal("0"), volume=999),
                SimpleNamespace(price=Decimal("1100"), volume=99),
            ],
        ))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 1),
            price=Decimal("1100"),
            volume=10,
            cum_volume=100,
            is_limit_up_price=True,
            is_limit_up_bid=False,
        ))

        self.assertFalse(engine._states["2330"].is_at_limit_up)
        self.assertFalse(engine._states["2330"].limit_up_candidate_states["strict_lock_with_effective_bid_tick_confirmed"])

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 2),
            price=Decimal("1100"),
            volume=10,
            cum_volume=110,
            is_limit_up_price=True,
            is_limit_up_bid=True,
        ))

        self.assertTrue(engine._states["2330"].is_at_limit_up)
        self.assertTrue(engine._states["2330"].limit_up_candidate_states["strict_lock_with_effective_bid_tick_confirmed"])

    def test_tick_confirmed_lock_does_not_reuse_stale_tick_from_previous_segment(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="strict_lock_with_effective_bid_tick_confirmed",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 11, 5, 40),
            price=Decimal("1100"),
            volume=10,
            is_limit_up_price=True,
            is_limit_up_bid=True,
        ))
        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 11, 5, 45),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))

        state = engine._states["2330"]
        self.assertTrue(state.limit_up_candidate_states["strict_lock_with_effective_bid"])
        self.assertFalse(state.limit_up_candidate_states["strict_lock_with_effective_bid_tick_confirmed"])
        self.assertFalse(state.is_at_limit_up)

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 11, 5, 52),
            price=Decimal("1100"),
            volume=10,
            is_limit_up_price=True,
            is_limit_up_bid=True,
        ))

        self.assertTrue(state.limit_up_candidate_states["strict_lock_with_effective_bid_tick_confirmed"])
        self.assertTrue(state.is_at_limit_up)

    def test_strict_lock_keeps_candidate_time_before_confirmed_lock(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f11_enabled=False,
            per_stock_amount=2_000_000,
            limit_up_detection_mode="strict_lock_from_user_rule",
        )
        decision_events = []
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            on_decision_event=decision_events.append,
        )
        engine._running = True

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 32, 16),
            price=Decimal("1100"),
            volume=10,
            is_limit_up_price=True,
        ))

        state = engine._states["2330"]
        self.assertIsNotNone(state.first_limit_up_candidate_event_time)
        self.assertEqual(
            state.first_limit_up_candidate_event_time,
            datetime(2026, 5, 19, 9, 32, 16),
        )
        self.assertIsNone(state.first_limit_up_confirmed_event_time)
        self.assertFalse(state.is_at_limit_up)
        self.assertFalse(state.pending)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 32, 24),
            ask=[],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 32, 24, 500000),
            price=Decimal("1100"),
            volume=5,
            is_limit_up_price=True,
        ))

        self.assertEqual(
            state.first_limit_up_confirmed_event_time,
            datetime(2026, 5, 19, 9, 32, 24),
        )
        self.assertTrue(state.is_at_limit_up)
        self.assertTrue(state.pending)
        self.assertTrue(
            any(ev.get("category") == "LIMIT_UP_CANDIDATE" for ev in decision_events)
        )
        self.assertEqual(
            decision_events[-1]["details"]["confirmed_lock_event_time"],
            "2026-05-19T09:32:24",
        )

    def test_update_limitup_mode_refreshes_state_and_summary_signals(self):
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            limit_up_detection_mode="bid_and_zero_ask",
        )
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            ask=[SimpleNamespace(price=Decimal("1100"), volume=3)],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=99)],
        ))

        state = engine._states["2330"]
        self.assertFalse(state.is_at_limit_up)
        self.assertTrue(state.limit_up_signal_states["bid_at_limit"])
        self.assertFalse(state.limit_up_candidate_states["bid_and_zero_ask"])

        engine.update_limit_up_mode("bid_only")

        summary = {item["code"]: item for item in engine.get_summary()}
        self.assertEqual(state.active_limit_up_mode, "strict_lock_with_effective_bid_tick_confirmed")
        self.assertFalse(state.is_at_limit_up)
        self.assertEqual(summary["2330"]["limit_up_mode"], "strict_lock_with_effective_bid_tick_confirmed")
        self.assertTrue(summary["2330"]["limit_up_signals"]["bid_at_limit"])
        self.assertFalse(summary["2330"]["limit_up_candidates"]["strict_lock_with_effective_bid_tick_confirmed"])

    def test_skip_entry_emits_decision_detail_event(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f10_enabled=False,
            entry_before_time="23:59",
            start_time="09:31",
        )
        decision_events = []
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            on_decision_event=decision_events.append,
        )
        engine._current_datetime = lambda: datetime(2026, 5, 19, 9, 30, 0)
        state = self._arm_entry_state(engine)
        state.last_price = Decimal(str(state.info.limit_up))

        engine._tick(state, time.time())

        self.assertTrue(decision_events)
        self.assertEqual(decision_events[-1]["category"], "ENTRY_SKIP")
        self.assertEqual(decision_events[-1]["result"], "未進場")
        self.assertIn("未到開始時間", decision_events[-1]["reason"])

    def test_decision_event_includes_market_recv_and_decision_timing(self):
        decision_events = []
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f11_enabled=False,
            limit_up_detection_mode="ask_or_bid_or_last",
        )
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            on_decision_event=decision_events.append,
        )
        market_time = datetime(2026, 5, 19, 9, 32, 16, 123000)
        recv_time = datetime(2026, 5, 19, 9, 32, 19, 456000)

        engine._on_tick(TickEvent(
            code="2330",
            time=market_time,
            recv_time=recv_time,
            price=Decimal("1100"),
            volume=10,
        ))

        self.assertTrue(decision_events)
        event = decision_events[-1]
        details = event["details"]
        self.assertEqual(event["market_event_time"], market_time.isoformat())
        self.assertEqual(event["recv_time"], recv_time.isoformat())
        self.assertEqual(details["market_event_time"], market_time.isoformat())
        self.assertEqual(details["recv_time"], recv_time.isoformat())
        self.assertIsInstance(details["decision_time"], str)
        self.assertEqual(details["market_to_recv_ms"], 3333.0)
        self.assertGreaterEqual(details["recv_to_decision_ms"], 0.0)
        self.assertGreaterEqual(details["market_to_decision_ms"], 3333.0)

    def test_limit_up_event_triggers_entry_without_waiting_for_tick_loop(self):
        class FakeBroker:
            def __init__(self):
                self.orders = []

            def place_order(self, req):
                self.orders.append(req)
                return "O1"

        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f11_enabled=False,
            limit_up_detection_mode="ask_or_bid_or_last",
            per_stock_amount=2_000_000,
        )
        broker = FakeBroker()
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            broker=broker,
        )
        engine._running = True

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            price=Decimal("1100"),
            volume=10,
        ))

        state = engine._states["2330"]
        self.assertTrue(state.pending)
        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(broker.orders[0].code, "2330")

    def test_limit_up_event_does_not_repeat_buy_within_same_lock_segment(self):
        class FakeBroker:
            def __init__(self):
                self.orders = []

            def place_order(self, req):
                self.orders.append(req)
                return "O1"

        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f11_enabled=False,
            limit_up_detection_mode="ask_or_bid_or_last",
            per_stock_amount=2_000_000,
        )
        broker = FakeBroker()
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            broker=broker,
        )
        engine._running = True

        limit_up = Decimal(str(engine._states["2330"].info.limit_up))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            price=limit_up,
            volume=10,
        ))
        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 0, 500000),
            ask=[],
            bid=[SimpleNamespace(price=limit_up, volume=99)],
        ))

        self.assertEqual(len(broker.orders), 1)

    def test_open_board_sell_triggers_without_waiting_for_tick_loop(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f5_enabled=False,
            f4_open_ticks_to_sell=1,
        )
        engine, _logs, trades, strategy_events = self._make_engine(cfg)
        engine._running = True
        engine._current_datetime = lambda: datetime(2026, 5, 19, 9, 1, 0)
        state = self._arm_exit_state(engine)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 0, 500000),
            ask=[SimpleNamespace(price=Decimal("1095"), volume=10)],
            bid=[SimpleNamespace(price=Decimal("1090"), volume=50)],
        ))

        self.assertEqual(state.position_qty, 0)
        self.assertEqual(trades[-1]["action"], "SELL")
        self.assertEqual(strategy_events[-1]["strategy"], "F4")

    def test_order_decision_event_includes_decision_to_order_latency(self):
        class FakeBroker:
            def __init__(self):
                self.orders = []

            def place_order(self, req):
                self.orders.append(req)
                return "O1"

        decision_events = []
        cfg = TradingConfig(
            f1_enabled=False,
            f9_enabled=False,
            f10_enabled=False,
            f11_enabled=False,
            limit_up_detection_mode="ask_or_bid_or_last",
            per_stock_amount=2_000_000,
        )
        broker = FakeBroker()
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            on_decision_event=decision_events.append,
            broker=broker,
        )
        engine._running = True

        limit_up = Decimal(str(engine._states["2330"].info.limit_up))
        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1),
            price=limit_up,
            volume=10,
        ))
        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 5, 19, 9, 1, 0, 500000),
            ask=[],
            bid=[SimpleNamespace(price=limit_up, volume=99)],
        ))

        engine._on_broker_order(OrderEvent(
            order_id="O1",
            code="2330",
            side=OrderSide.BUY,
            price=limit_up,
            qty=1,
            filled_qty=0,
            status=OrderStatus.PENDING,
            time=datetime(2026, 5, 19, 9, 1, 1),
            name="台積電",
            source="TEST",
        ))

        event = decision_events[-1]
        details = event["details"]
        self.assertEqual(event["category"], "ORDER")
        self.assertEqual(event["result"], "委託PENDING")
        self.assertEqual(details["source"], "TEST")
        self.assertIsInstance(details["trigger_decision_time"], str)
        self.assertIsInstance(details["local_order_submit_time"], str)
        self.assertIsInstance(details["decision_to_order_ms"], float)
        self.assertGreaterEqual(details["decision_to_order_ms"], 0.0)

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

    def test_f6_only_cancels_pending_buy_order(self):
        class FakeBroker:
            def __init__(self):
                self.cancelled = []

            def cancel_order(self, order_id):
                self.cancelled.append(order_id)
                return True

        cfg = TradingConfig(f9_enabled=False, f6_enabled=True)
        engine, _logs, _trades, strategy_events = self._make_engine(cfg)
        engine.broker = FakeBroker()
        state = engine._states["2330"]
        state.pending = True
        state.pending_side = "BUY"
        state.pending_order_id = "B1"
        now = time.time()
        state.tick_vols.append((now, 600))

        engine._tick(state, now)

        self.assertEqual(engine.broker.cancelled, ["B1"])
        self.assertFalse(state.pending)
        self.assertEqual(state.entry_blocked_reason, "爆量取消")
        self.assertEqual(strategy_events[-1]["strategy"], "F6")

    def test_f6_does_not_cancel_pending_sell_order(self):
        class FakeBroker:
            def __init__(self):
                self.cancelled = []

            def cancel_order(self, order_id):
                self.cancelled.append(order_id)
                return True

        cfg = TradingConfig(f9_enabled=False, f6_enabled=True, f4_enabled=False, f5_enabled=False)
        engine, _logs, _trades, _strategy_events = self._make_engine(cfg)
        engine.broker = FakeBroker()
        state = engine._states["2330"]
        state.position_qty = 1
        state.entry_price = Decimal("1100")
        state.pending = True
        state.pending_side = "SELL"
        state.pending_order_id = "S1"
        now = time.time()
        state.tick_vols.append((now, 600))

        engine._tick(state, now)

        self.assertEqual(engine.broker.cancelled, [])
        self.assertTrue(state.pending)
        self.assertEqual(state.pending_side, "SELL")

    def test_buy_fill_resets_pre_entry_volume_before_f5_sell_check(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_enabled=False,
            f5_enabled=True,
            volume_spike_sell_threshold=499,
        )
        engine, _logs, trades, strategy_events = self._make_engine(cfg)
        state = engine._states["2330"]
        now = time.time()
        state.pending = True
        state.pending_side = "BUY"
        state.pending_order_id = "B1"
        state.candle_index = 1
        state.is_at_limit_up = True
        state.last_price = Decimal(str(state.info.limit_up))
        state.tick_vols.append((now, 600))
        state.last_1s_vol = 600

        engine._on_broker_fill(SimpleNamespace(
            order_id="B1",
            side=OrderSide.BUY,
            code="2330",
            price=Decimal(str(state.info.limit_up)),
            qty=1,
            time=datetime.fromtimestamp(now),
        ))
        engine._tick(state, now)

        self.assertEqual(state.position_qty, 1)
        self.assertEqual(state.last_1s_vol, 0)
        self.assertEqual([ev["strategy"] for ev in strategy_events if ev["side"] == "SELL"], [])
        self.assertTrue(all(trade["action"] != "SELL" for trade in trades))

    def test_backfill_tick_does_not_update_volume_or_trigger_sell(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_enabled=False,
            f5_enabled=True,
            volume_spike_sell_threshold=499,
        )
        engine, logs, trades, strategy_events = self._make_engine(cfg)
        state = self._arm_exit_state(engine)

        engine._on_tick(TickEvent(
            code="2330",
            time=datetime(2026, 6, 16, 9, 44, 18, 759252),
            price=Decimal("1100"),
            volume=600,
            is_backfill=True,
        ))

        self.assertEqual(state.last_1s_vol, 0)
        self.assertEqual(state.position_qty, 1)
        self.assertEqual(trades, [])
        self.assertEqual(strategy_events, [])
        self.assertTrue(any("忽略 backfill tick" in msg for _level, msg in logs))

    def test_backfill_book_does_not_open_board_and_trigger_f4(self):
        cfg = TradingConfig(
            f9_enabled=False,
            f4_enabled=True,
            f5_enabled=False,
            f4_open_ticks_to_sell=1,
        )
        engine, logs, trades, strategy_events = self._make_engine(cfg)
        state = self._arm_exit_state(engine)

        engine._on_book(BookEvent(
            code="2330",
            time=datetime(2026, 6, 16, 9, 44, 21, 520107),
            ask=[SimpleNamespace(price=Decimal("1095"), volume=10)],
            bid=[SimpleNamespace(price=Decimal("1100"), volume=50)],
            is_backfill=True,
        ))

        self.assertEqual(state.ask0_price, Decimal(str(state.info.limit_up)))
        self.assertEqual(state.position_qty, 1)
        self.assertEqual(trades, [])
        self.assertEqual(strategy_events, [])
        self.assertTrue(any("忽略 backfill book" in msg for _level, msg in logs))

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

    def test_preloaded_symbol_info_skips_hot_path_special_lookup(self):
        class FakeBroker:
            def __init__(self):
                self.orders = []

            def load_symbol_info(self, codes):
                raise AssertionError(f"unexpected hot-path special lookup: {codes}")

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
        engine = TradingEngine(
            cfg,
            on_log=lambda _level, _msg: None,
            on_trade=lambda _trade: None,
            on_status=lambda _summary: None,
            broker=broker,
            symbol_infos={
                "2330": build_symbol_info(
                    "2330",
                    "台積電",
                    "TSE",
                    Decimal("1000"),
                    is_disposal=False,
                    is_attention=False,
                    is_day_trade_restricted=False,
                    prior_limit_up_streak=0,
                )
            },
        )
        state = self._arm_entry_state(engine, "2330")

        engine._tick(state, time.time())

        self.assertEqual(len(broker.orders), 1)
        self.assertTrue(state.special_check_completed)

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

    def test_clock_skew_monitor_reports_median_and_triggers_error_level(self):
        from datetime import timedelta

        cfg = TradingConfig()
        engine, logs, _trades, _events = self._make_engine(cfg)
        snaps = []
        engine.on_clock_skew = snaps.append

        now = datetime.now()
        for _ in range(10):
            engine._clock_skew_monitor.add_sample(
                now - timedelta(milliseconds=3500),
                now,
            )

        engine._clock_skew_last_report_ts = 0.0
        engine._maybe_report_clock_skew(time.time())

        self.assertEqual(len(snaps), 1)
        self.assertGreaterEqual(snaps[0]["median_ms"], 3000.0)
        self.assertEqual(snaps[0]["level"], "ERROR")
        self.assertTrue(any(level == "ERROR" and "時鐘偏移" in msg for level, msg in logs))

    def test_clock_skew_monitor_below_info_threshold_does_not_log(self):
        from datetime import timedelta

        cfg = TradingConfig()
        engine, logs, _trades, _events = self._make_engine(cfg)
        snaps = []
        engine.on_clock_skew = snaps.append

        now = datetime.now()
        for _ in range(10):
            engine._clock_skew_monitor.add_sample(
                now - timedelta(milliseconds=50),
                now,
            )

        engine._clock_skew_last_report_ts = 0.0
        engine._maybe_report_clock_skew(time.time())

        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["level"], "")
        self.assertFalse(any("時鐘偏移" in msg for _level, msg in logs))


if __name__ == "__main__":
    unittest.main()
