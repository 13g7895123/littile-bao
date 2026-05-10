"""
engine.TradingEngine strategy behavior tests.
"""
import os
import sys
import time
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

    def test_consume_entry_skips_f1_when_mutex_enabled(self):
        cfg = TradingConfig(
            entry_before_time="00:00",
            ask_queue_threshold=1,
            f9_enabled=False,
            f10_enabled=False,
            f_consume_enabled=True,
            consume_qty_threshold=10,
            consume_mutex_with_f1=True,
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
