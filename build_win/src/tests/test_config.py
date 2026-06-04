"""
config.TradingConfig 單元測試。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import AppState, LOCKED_LIMIT_UP_DETECTION_MODE, TradingConfig  # noqa: E402


class TestTradingConfigJsonIO(unittest.TestCase):
    def test_load_strict_reads_custom_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "import.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "start_time": "09:05",
                        "entry_before_time": "09:30",
                        "per_stock_amount": 250000,
                        "f4_open_ticks_to_sell": 3,
                        "f4_require_today_limitup": False,
                        "f_open_limitup_entry_enabled": False,
                        "f_consume_enabled": True,
                        "consume_qty_threshold": 300,
                        "consume_mutex_with_f1": False,
                        "file_logging_enabled": False,
                        "unknown_field": "ignored",
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            cfg = TradingConfig.load_strict(path)

            self.assertEqual(cfg.start_time, "09:05")
            self.assertEqual(cfg.entry_before_time, "09:30")
            self.assertEqual(cfg.per_stock_amount, 250000)
            self.assertEqual(cfg.f4_open_ticks_to_sell, 3)
            self.assertFalse(cfg.f4_require_today_limitup)
            self.assertFalse(cfg.f_open_limitup_entry_enabled)
            self.assertTrue(cfg.f_consume_enabled)
            self.assertEqual(cfg.consume_qty_threshold, 300)
            self.assertFalse(cfg.consume_mutex_with_f1)
            self.assertFalse(cfg.file_logging_enabled)
            self.assertEqual(cfg.limit_up_detection_mode, LOCKED_LIMIT_UP_DETECTION_MODE)

    def test_load_strict_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "broken.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken json")

            with self.assertRaises(json.JSONDecodeError):
                TradingConfig.load_strict(path)

    def test_from_dict_rejects_non_object_root(self):
        with self.assertRaises(ValueError):
            TradingConfig.from_dict(["not", "an", "object"])

    def test_from_dict_migrates_old_limitup_mode(self):
        cfg = TradingConfig.from_dict({
            "limit_up_detection_mode": "ask_or_bid_or_last",
        })

        self.assertEqual(cfg.limit_up_detection_mode, LOCKED_LIMIT_UP_DETECTION_MODE)


class TestAppStateJsonIO(unittest.TestCase):
    def test_app_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "app_state.json")
            state = AppState(
                last_trading_config_path="/tmp/trading_import.json",
                last_broker_settings_path="/tmp/broker_import.json",
            )

            state.save(path)
            loaded = AppState.load_strict(path)

            self.assertEqual(loaded.last_trading_config_path, "/tmp/trading_import.json")
            self.assertEqual(loaded.last_broker_settings_path, "/tmp/broker_import.json")

    def test_from_dict_migrates_previous_default_limitup_mode(self):
        cfg = TradingConfig.from_dict({
            "limit_up_detection_mode": "bid_and_zero_ask",
        })

        self.assertEqual(cfg.limit_up_detection_mode, LOCKED_LIMIT_UP_DETECTION_MODE)


if __name__ == "__main__":
    unittest.main()
