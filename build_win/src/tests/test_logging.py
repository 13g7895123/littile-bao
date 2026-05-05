"""
app_logging 與 TradingConfig 的單元測試。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_logging import _TeeStream, compose_log_message, configure_runtime_logging, write_log_event  # noqa: E402
from config import TradingConfig  # noqa: E402


class TestTradingConfigLogging(unittest.TestCase):
    def test_file_logging_flag_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            TradingConfig(file_logging_enabled=False, per_stock_amount=200000).save(path)

            loaded = TradingConfig.load(path)

            self.assertFalse(loaded.file_logging_enabled)
            self.assertEqual(loaded.per_stock_amount, 200000)


class TestRuntimeLogging(unittest.TestCase):
    def tearDown(self):
        configure_runtime_logging(False)

    def test_compose_log_message_appends_traceback(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            message = compose_log_message("ERROR", "測試錯誤")

        self.assertIn("Traceback", message)
        self.assertIn("RuntimeError: boom", message)

    def test_enabled_runtime_logging_writes_event_and_stdout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = configure_runtime_logging(True, base_dir=tmpdir)

            write_log_event("INFO", "事件已寫入")
            print("stdout 測試訊息")
            sys.stdout.flush()
            configure_runtime_logging(False, base_dir=tmpdir)

            self.assertIsNotNone(log_path)
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("[INFO] 事件已寫入", content)
            self.assertIn("[STDOUT] stdout 測試訊息", content)

    def test_tee_stream_handles_missing_underlying_stream(self):
        captured = []

        class DummyManager:
            def write_stream(self, name: str, data: str) -> None:
                captured.append((name, data))

        stream = _TeeStream(DummyManager(), None, "STDOUT")

        written = stream.write("no-console mode")
        stream.flush()

        self.assertEqual(written, len("no-console mode"))
        self.assertEqual(captured, [("STDOUT", "no-console mode")])


if __name__ == "__main__":
    unittest.main()