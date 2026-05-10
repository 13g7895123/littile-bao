"""
broker.universe 單元測試。
"""
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker.universe import (  # noqa: E402
    DEFAULT_MOCK_INFOS,
    FubonSymbolInfoLoader,
    MarketSnapshotCache,
    PreviousTradingDaysApiClient,
    PreviousTradingDaysCache,
    ScanCriteria,
    StaticSymbolInfoLoader,
    build_symbol_info,
    calc_limit_down,
    calc_limit_up,
    is_limit_up_close,
    resolve_preview_price,
    scan_daily,
    scan_preview_candidates,
    tick_size,
)


class TestTickSize(unittest.TestCase):
    def test_below_10(self):
        self.assertEqual(tick_size(Decimal("9.5")), Decimal("0.01"))

    def test_10_to_50(self):
        self.assertEqual(tick_size(Decimal("25")), Decimal("0.05"))

    def test_50_to_100(self):
        self.assertEqual(tick_size(Decimal("88")), Decimal("0.1"))

    def test_100_to_500(self):
        self.assertEqual(tick_size(Decimal("250")), Decimal("0.5"))

    def test_500_to_1000(self):
        self.assertEqual(tick_size(Decimal("777")), Decimal("1"))

    def test_above_1000(self):
        self.assertEqual(tick_size(Decimal("1500")), Decimal("5"))


class TestLimitPriceCalc(unittest.TestCase):
    def test_limit_up_simple(self):
        # 100 × 1.1 = 110，tick=0.5（100~500 區間）
        self.assertEqual(calc_limit_up(Decimal("100")), Decimal("110"))

    def test_limit_up_tick_floor(self):
        # 25 × 1.1 = 27.5，tick=0.05
        self.assertEqual(calc_limit_up(Decimal("25")), Decimal("27.5"))

    def test_limit_down(self):
        # 100 × 0.9 = 90，tick=0.1
        self.assertEqual(calc_limit_down(Decimal("100")), Decimal("90"))

    def test_high_price_tick(self):
        # 1000 × 1.1 = 1100，tick=5
        result = calc_limit_up(Decimal("1000"))
        self.assertEqual(result % Decimal("5"), Decimal("0"))

    def test_is_limit_up_close(self):
        self.assertTrue(is_limit_up_close(Decimal("110"), Decimal("100")))
        self.assertFalse(is_limit_up_close(Decimal("109.5"), Decimal("100")))


class TestBuildSymbolInfo(unittest.TestCase):
    def test_basic(self):
        si = build_symbol_info("2330", "台積電", "TSE", 1000.0)
        self.assertEqual(si.code, "2330")
        self.assertEqual(si.market, "TSE")
        self.assertEqual(si.prev_close, Decimal("1000"))
        self.assertIsNone(si.quote_price)
        # 漲停應接近 1100，跌停接近 900
        self.assertGreater(si.limit_up_price, Decimal("1090"))
        self.assertLess(si.limit_down_price, Decimal("910"))

    def test_special_flags(self):
        si = build_symbol_info("2454", "聯發科", "TSE", 1300.0, is_disposal=True)
        self.assertTrue(si.is_disposal)
        self.assertFalse(si.is_attention)


class TestStaticLoader(unittest.TestCase):
    def test_load_filters_codes(self):
        infos = {i.code: i for i in DEFAULT_MOCK_INFOS}
        loader = StaticSymbolInfoLoader(infos)
        out = loader.load(["2330", "0000"])  # 0000 不存在
        self.assertIn("2330", out)
        self.assertNotIn("0000", out)


class TestMockAdapterLoadSymbolInfo(unittest.TestCase):
    def test_load_via_mock_adapter(self):
        from broker import MockAdapter
        m = MockAdapter()
        m.login()
        out = m.load_symbol_info(["2330", "2317"])
        self.assertEqual(set(out.keys()), {"2330", "2317"})
        self.assertGreater(out["2330"].limit_up_price, out["2330"].prev_close)


class TestPreviewPriceFiltering(unittest.TestCase):
    def test_resolve_preview_price_falls_back_to_prev_close(self):
        info = build_symbol_info("2330", "台積電", "TSE", 1000.0)
        self.assertEqual(resolve_preview_price(info), Decimal("1000"))

    def test_preview_scan_uses_quote_price_not_limit_up(self):
        infos = [
            build_symbol_info("1111", "甲", "TSE", 100.0, quote_price=Decimal("85"), prev_volume=5000),
            build_symbol_info("2222", "乙", "TSE", 100.0, quote_price=Decimal("120"), prev_volume=6000),
        ]
        crit = ScanCriteria(
            price_min=Decimal("80"),
            price_max=Decimal("90"),
            min_prev_volume=0,
            exclude_disposal=False,
            exclude_attention=False,
            exclude_day_trade_restricted=False,
            markets=("TSE",),
            max_candidates=10,
        )

        preview = scan_preview_candidates(infos, crit)
        strategy = scan_daily(infos, crit)

        self.assertEqual([i.code for i in preview], ["1111"])
        self.assertEqual(strategy, [])

    def test_fubon_parse_item_reads_quote_price(self):
        class DummyAdapter:
            sdk = object()

        loader = FubonSymbolInfoLoader(DummyAdapter())
        info = loader._parse_item({
            "symbol": "2330",
            "name": "台積電",
            "market": "TSE",
            "previousClose": 100,
            "closePrice": 88.5,
            "totalVolume": 12345,
        })

        self.assertIsNotNone(info)
        self.assertEqual(info.quote_price, Decimal("88.5"))
        self.assertEqual(info.prev_volume, 12345)

    def test_fubon_parse_item_skips_zero_close_price(self):
        class DummyAdapter:
            sdk = object()

        loader = FubonSymbolInfoLoader(DummyAdapter())
        info = loader._parse_item({
            "symbol": "4919",
            "name": "新唐",
            "exchange": "TPEx",
            "previousClose": 210,
            "closePrice": "0",
            "lastPrice": "232.5",
            "previousVolume": 4567,
        })

        self.assertIsNotNone(info)
        self.assertEqual(info.market, "OTC")
        self.assertEqual(info.quote_price, Decimal("232.5"))
        self.assertEqual(info.prev_volume, 4567)


class TestPriorLimitUpStreak(unittest.TestCase):
    def test_cache_computes_two_day_limit_up_streak(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = MarketSnapshotCache(os.path.join(tmpdir, "snapshots.json"))
            cache.store_snapshot([
                build_symbol_info(
                    "1111", "甲", "TSE", 100,
                    quote_price=Decimal("110"), prev_volume=5000,
                )
            ], "2026-05-05")
            cache.store_snapshot([
                build_symbol_info(
                    "1111", "甲", "TSE", 110,
                    quote_price=Decimal("121"), prev_volume=6000,
                )
            ], "2026-05-06")

            today = build_symbol_info(
                "1111", "甲", "TSE", 121, prev_volume=7000)
            updated = cache.apply_prior_limit_up_streaks([today], max_days=2)

        self.assertEqual(updated, 1)
        self.assertEqual(today.prior_limit_up_streak, 2)

    def test_scan_daily_excludes_over_prior_limit_up_streak(self):
        info = build_symbol_info(
            "1111", "甲", "TSE", 121,
            prev_volume=7000,
            prior_limit_up_streak=1,
        )
        crit = ScanCriteria(
            min_prev_volume=0,
            exclude_disposal=False,
            exclude_attention=False,
            exclude_day_trade_restricted=False,
            markets=("TSE",),
            max_candidates=10,
            max_prior_limit_up_streak=0,
        )

        self.assertEqual(scan_daily([info], crit), [])

        crit.max_prior_limit_up_streak = 1
        self.assertEqual([item.code for item in scan_daily([info], crit)], ["1111"])

    def test_unknown_prior_streak_is_kept_conservatively(self):
        info = build_symbol_info("1111", "甲", "TSE", 100, prev_volume=7000)
        crit = ScanCriteria(
            min_prev_volume=0,
            exclude_disposal=False,
            exclude_attention=False,
            exclude_day_trade_restricted=False,
            markets=("TSE",),
            max_prior_limit_up_streak=0,
        )

        self.assertEqual([item.code for item in scan_daily([info], crit)], ["1111"])


class TestFubonMarketSnapshots(unittest.TestCase):
    def test_load_market_snapshots_uses_close_price_and_market_fallback(self):
        class FakeSnapshot:
            def __init__(self):
                self.calls = []

            def quotes(self, **kwargs):
                self.calls.append(kwargs)
                market = kwargs.get("market")
                if market == "TSE":
                    return {"data": [{
                        "symbol": "2330",
                        "name": "台積電",
                        "closePrice": "88.5",
                        "change": "-1.5",
                        "tradeVolume": "12345",
                    }]}
                return {"data": [{
                    "symbol": "4919",
                    "name": "新唐",
                    "closePrice": "52",
                    "change": "2",
                    "tradeVolume": "4567",
                }]}

        class FakeSdk:
            def __init__(self, snapshot):
                self.init_count = 0
                self.marketdata = SimpleNamespace(
                    rest_client=SimpleNamespace(
                        stock=SimpleNamespace(snapshot=snapshot)
                    )
                )

            def init_realtime(self):
                self.init_count += 1

        snapshot = FakeSnapshot()
        sdk = FakeSdk(snapshot)
        adapter = SimpleNamespace(sdk=sdk)

        loader = FubonSymbolInfoLoader(adapter)
        infos = loader.load_market_snapshots(["TSE", "OTC"])

        self.assertEqual(sdk.init_count, 1)
        self.assertEqual(snapshot.calls[0], {"market": "TSE", "type": "COMMONSTOCK"})
        self.assertEqual(snapshot.calls[1], {"market": "OTC", "type": "COMMONSTOCK"})
        self.assertEqual(infos["2330"].quote_price, Decimal("88.5"))
        self.assertEqual(infos["2330"].prev_close, Decimal("90.0"))
        self.assertEqual(infos["2330"].prev_volume, 12345)
        self.assertEqual(infos["4919"].market, "OTC")

    def test_load_market_snapshots_can_store_close_cache(self):
        class FakeSnapshot:
            def quotes(self, **kwargs):
                return {"date": "2026-05-06", "data": [{
                    "symbol": "1111",
                    "name": "甲",
                    "previousClose": "110",
                    "closePrice": "121",
                    "tradeVolume": "5000",
                }]}

        class FakeSdk:
            def __init__(self):
                self.marketdata = SimpleNamespace(
                    rest_client=SimpleNamespace(
                        stock=SimpleNamespace(snapshot=FakeSnapshot())
                    )
                )

            def init_realtime(self):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = MarketSnapshotCache(os.path.join(tmpdir, "snapshots.json"))
            loader = FubonSymbolInfoLoader(SimpleNamespace(sdk=FakeSdk()))
            loader.load_market_snapshots(
                ["TSE"], snapshot_cache=cache, cache_snapshots=True)
            today = build_symbol_info("1111", "甲", "TSE", 121, prev_volume=1)
            cache.apply_prior_limit_up_streaks([today], max_days=1)

        self.assertEqual(today.prior_limit_up_streak, 1)

    def test_market_snapshot_infos_filter_by_preview_price(self):
        infos = [
            build_symbol_info("1111", "甲", "TSE", 90, quote_price=Decimal("88")),
            build_symbol_info("2222", "乙", "OTC", 110, quote_price=Decimal("120")),
        ]
        crit = ScanCriteria(
            price_min=Decimal("80"),
            price_max=Decimal("90"),
            min_prev_volume=0,
            exclude_disposal=False,
            exclude_attention=False,
            exclude_day_trade_restricted=False,
            markets=("TSE", "OTC"),
            max_candidates=10,
        )

        self.assertEqual(
            [info.code for info in scan_preview_candidates(infos, crit)],
            ["1111"],
        )


class TestPreviousTradingDaysApi(unittest.TestCase):
    def test_default_api_url_is_production_endpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = PreviousTradingDaysApiClient(
                cache=PreviousTradingDaysCache(os.path.join(tmpdir, "previous.json")),
            )

        self.assertEqual(
            client.base_url,
            "https://stock.try-8verything.com/api/prices/previous-trading-days",
        )

    def test_api_request_uses_browser_user_agent(self):
        headers = PreviousTradingDaysApiClient._request_headers()

        self.assertEqual(headers["Accept"], "application/json")
        self.assertIn("Mozilla/5.0", headers["User-Agent"])

    def test_load_symbol_infos_fetches_once_and_reuses_daily_cache(self):
        payload = {
            "as_of": "2026-05-10",
            "count": 2,
            "data": [
                {
                    "symbol": "1111",
                    "name": "甲",
                    "market": "TWSE",
                    "data": [
                        {"date": "2026-05-08", "close": "110", "volume": "2000"},
                        {"date": "2026-05-07", "close": "100", "volume": "1500"},
                    ],
                },
                {
                    "symbol": "2222",
                    "name": "乙",
                    "market": "TPEX",
                    "data": [
                        {"date": "2026-05-08", "close": "80", "volume": "900"},
                        {"date": "2026-05-07", "close": "82", "volume": "800"},
                    ],
                },
            ],
        }

        class FakeClient(PreviousTradingDaysApiClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.calls = []

            def _fetch_json(self, url: str) -> dict:
                self.calls.append(url)
                return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "previous.json")
            client = FakeClient(
                "http://example.test/api/prices/previous-trading-days",
                cache=PreviousTradingDaysCache(cache_path),
            )

            infos = client.load_symbol_infos(["TSE"], as_of="2026-05-10")

            self.assertFalse(client.last_from_cache)
            self.assertEqual(len(client.calls), 1)
            self.assertIn("as_of=2026-05-10", client.calls[0])
            self.assertEqual(list(infos.keys()), ["1111"])
            self.assertEqual(infos["1111"].prev_close, Decimal("110"))
            self.assertEqual(infos["1111"].quote_price, Decimal("110"))
            self.assertEqual(infos["1111"].prev_volume, 2000)
            self.assertEqual(infos["1111"].prior_limit_up_streak, 1)
            self.assertEqual(infos["1111"].display_prev_close, Decimal("100"))
            self.assertTrue(infos["1111"].closed_at_limit_up)

            cached_client = FakeClient(
                "http://example.test/api/prices/previous-trading-days",
                cache=PreviousTradingDaysCache(cache_path),
            )
            cached_infos = cached_client.load_symbol_infos(["TSE", "OTC"], as_of="2026-05-10")

            self.assertTrue(cached_client.last_from_cache)
            self.assertEqual(cached_client.calls, [])
            self.assertEqual(set(cached_infos.keys()), {"1111", "2222"})


if __name__ == "__main__":
    unittest.main()
