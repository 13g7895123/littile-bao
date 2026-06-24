"""
Windows time synchronization helper tests.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import windows_time_sync  # noqa: E402


class TestWindowsTimeSync(unittest.TestCase):
    def setUp(self):
        windows_time_sync._LAST_RESULT = None
        windows_time_sync._LAST_RESULT_MONOTONIC = None

    def test_parse_stripchart_offsets(self):
        output = """
09:58:26, +00.0002396s
09:58:28, -00.0000407s
09:58:30, -00.0002116s
"""

        offsets = windows_time_sync.parse_stripchart_offsets(output)

        self.assertEqual(offsets, [0.0002396, -0.0000407, -0.0002116])

    def test_verify_and_repair_skips_when_offset_is_within_threshold(self):
        calls = []

        def fake_run_command(args, timeout=30):
            calls.append(args)
            if args[0] == "w32tm" and "/stripchart" in args:
                return 0, "09:58:26, +00.0100000s\n09:58:28, +00.0120000s\n09:58:30, +00.0110000s"
            return 0, ""

        with patch.object(windows_time_sync, "is_windows", return_value=True), \
             patch.object(windows_time_sync, "run_command", side_effect=fake_run_command):
            result = windows_time_sync.verify_and_repair(threshold_seconds=0.05, samples=3)

        self.assertTrue(result.success)
        self.assertFalse(result.repaired)
        self.assertAlmostEqual(result.post_offset_seconds, 0.011)
        self.assertFalse(any("Set-Date" in " ".join(call) for call in calls))

    def test_verify_and_repair_step_corrects_when_offset_exceeds_threshold(self):
        stripchart_offsets = iter([
            "09:58:26, +00.3180000s\n09:58:28, +00.3180000s\n09:58:30, +00.3180000s",
            "09:58:36, +00.3180000s\n09:58:38, +00.3180000s\n09:58:40, +00.3180000s",
            "09:58:46, +00.0010000s\n09:58:48, +00.0010000s\n09:58:50, +00.0010000s",
        ])
        commands = []

        def fake_run_command(args, timeout=30):
            commands.append(args)
            if args[0] == "w32tm" and "/stripchart" in args:
                return 0, next(stripchart_offsets)
            if args[0] == "powershell.exe" and "Set-Date" in args[-1]:
                return 0, "2026-06-23T09:58:00.0000000+08:00"
            if args[0] == "powershell.exe" and "Get-Service" in args[-1]:
                return 0, "Running"
            return 0, "success"

        with patch.object(windows_time_sync, "is_windows", return_value=True), \
             patch.object(windows_time_sync, "run_command", side_effect=fake_run_command):
            result = windows_time_sync.verify_and_repair(threshold_seconds=0.05, samples=3)

        self.assertTrue(result.success)
        self.assertTrue(result.repaired)
        self.assertAlmostEqual(result.pre_offset_seconds, 0.318)
        self.assertAlmostEqual(result.post_offset_seconds, 0.001)
        self.assertTrue(any(cmd[0] == "powershell.exe" and "Set-Date" in cmd[-1] for cmd in commands))
        set_date_command = next(cmd[-1] for cmd in commands if cmd[0] == "powershell.exe" and "Set-Date" in cmd[-1])
        self.assertIn("AddSeconds(-0.318000000)", set_date_command)

    def test_verify_and_repair_cached_reuses_recent_result(self):
        calls = []

        def fake_run_command(args, timeout=30):
            calls.append(args)
            if args[0] == "w32tm" and "/stripchart" in args:
                return 0, "09:58:26, +00.0100000s\n09:58:28, +00.0120000s\n09:58:30, +00.0110000s"
            return 0, ""

        with patch.object(windows_time_sync, "is_windows", return_value=True), \
             patch.object(windows_time_sync, "run_command", side_effect=fake_run_command):
            first = windows_time_sync.verify_and_repair_cached(threshold_seconds=0.05, samples=3)
            second = windows_time_sync.verify_and_repair_cached(threshold_seconds=0.05, samples=3)

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(sum(1 for call in calls if call[0] == "w32tm" and "/stripchart" in call), 1)
        self.assertTrue(any("沿用" in note for note in second.notes))


if __name__ == "__main__":
    unittest.main()
