"""
app_logging 與 TradingConfig 的單元測試。
"""
import base64
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

    def test_runtime_logging_filters_encoded_sdk_noise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = configure_runtime_logging(True, base_dir=tmpdir)

            encoded_noise = base64.b64encode(
                b"[2026-05-05 11:46:58 +08:00 DEBUG sdk_core::transport::websocket_connection] Successfully connected to WebSocket: wss://example"
            ).decode("ascii")
            encoded_message = base64.b64encode(
                b"[2026-05-05 11:46:58 +08:00 INFO client] this account require 2fa"
            ).decode("ascii")

            print(encoded_noise)
            print(encoded_message)
            sys.stdout.flush()
            configure_runtime_logging(False, base_dir=tmpdir)

            self.assertIsNotNone(log_path)
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertNotIn("sdk_core::transport::websocket_connection", content)
            self.assertNotIn("Successfully connected to WebSocket", content)
            self.assertIn("[STDOUT] this account require 2fa", content)

    def test_runtime_logging_compacts_traceback_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = configure_runtime_logging(True, base_dir=tmpdir)

            write_log_event("ERROR", "載入失敗\nTraceback (most recent call last):\n  File \"x.py\", line 1, in <module>\n    raise RuntimeError('boom')\nRuntimeError: boom")
            sys.stderr.write("Traceback (most recent call last):\n")
            sys.stderr.write("  File \"x.py\", line 1, in <module>\n")
            sys.stderr.write("    raise ValueError('bad')\n")
            sys.stderr.write("ValueError: bad\n")
            sys.stderr.flush()
            configure_runtime_logging(False, base_dir=tmpdir)

            self.assertIsNotNone(log_path)
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("[ERROR] 載入失敗", content)
            self.assertIn("[ERROR] RuntimeError: boom", content)
            self.assertIn("[STDERR] ValueError: bad", content)
            self.assertNotIn("Traceback (most recent call last)", content)
            self.assertNotIn("File \"x.py\"", content)
            self.assertNotIn("raise RuntimeError", content)


if __name__ == "__main__":
    unittest.main()