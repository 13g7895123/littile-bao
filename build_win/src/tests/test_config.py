"""
config.TradingConfig 單元測試。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TradingConfig  # noqa: E402


class TestTradingConfigJsonIO(unittest.TestCase):
    def test_load_strict_reads_custom_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "import.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "entry_before_time": "09:30",
                        "per_stock_amount": 250000,
                        "file_logging_enabled": False,
                        "unknown_field": "ignored",
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            cfg = TradingConfig.load_strict(path)

            self.assertEqual(cfg.entry_before_time, "09:30")
            self.assertEqual(cfg.per_stock_amount, 250000)
            self.assertFalse(cfg.file_logging_enabled)

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


if __name__ == "__main__":
    unittest.main()