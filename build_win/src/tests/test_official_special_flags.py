import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import official_special_flags


class TestOfficialSpecialFlags(unittest.TestCase):
    def test_payload_fresh_requires_today_generation_and_market_dates(self):
        day = datetime(2026, 6, 23).date()
        payload = {
            "generated_date": "2026-06-23",
            "trade_date_roc": "1150623",
            "source_dates": {
                "twse_daytrade_daily": ["1150623"],
                "tpex_securities": ["1150623"],
            },
            "flags": {},
        }
        self.assertTrue(official_special_flags.is_payload_fresh(payload, day, ["TSE", "OTC"]))

        stale = dict(payload)
        stale["generated_date"] = "2026-06-22"
        self.assertFalse(official_special_flags.is_payload_fresh(stale, day, ["TSE", "OTC"]))

    def test_resolve_today_payload_uses_fresh_cache(self):
        now = datetime(2026, 6, 23, 9, 5)
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {
                "generated_date": "2026-06-23",
                "trade_date_roc": "1150623",
                "source_dates": {"twse_daytrade_daily": ["1150623"]},
                "flags": {"2330": {"is_attention": True}},
            }
            path = official_special_flags.cache_path(tmpdir, now.date())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")

            result, source = official_special_flags.resolve_today_payload(
                base_dir=tmpdir,
                markets=["TSE"],
                now=now,
                json_loader=lambda _url: (_ for _ in ()).throw(AssertionError("unexpected fetch")),
            )

        self.assertEqual(source, "cache")
        self.assertEqual(result["flags"]["2330"]["is_attention"], True)

    def test_resolve_today_payload_refetches_when_cache_is_stale(self):
        now = datetime(2026, 6, 23, 9, 5)
        with tempfile.TemporaryDirectory() as tmpdir:
            stale = {
                "generated_date": "2026-06-22",
                "trade_date_roc": "1150622",
                "source_dates": {"twse_daytrade_daily": ["1150622"]},
                "flags": {},
            }
            path = official_special_flags.cache_path(tmpdir, now.date())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(stale), encoding="utf-8")

            responses = {
                "https://openapi.twse.com.tw/v1/announcement/notice": [],
                "https://openapi.twse.com.tw/v1/announcement/punish": [],
                "https://openapi.twse.com.tw/v1/exchangeReport/TWTB4U": [
                    {"Date": "1150623", "Code": "2330", "Name": "台積電", "Suspension": ""}
                ],
                "https://openapi.twse.com.tw/v1/exchangeReport/TWTBAU1": [],
            }

            result, source = official_special_flags.resolve_today_payload(
                base_dir=tmpdir,
                markets=["TSE"],
                now=now,
                json_loader=lambda url: responses[url],
            )

            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(source, "api")
        self.assertEqual(result["trade_date_roc"], "1150623")
        self.assertEqual(saved["trade_date_roc"], "1150623")


if __name__ == "__main__":
    unittest.main()
