"""
broker.universe 單元測試。
"""
import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker.universe import (  # noqa: E402
    DEFAULT_MOCK_INFOS,
    FubonSymbolInfoLoader,
    ScanCriteria,
    StaticSymbolInfoLoader,
    build_symbol_info,
    calc_limit_down,
    calc_limit_up,
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


if __name__ == "__main__":
    unittest.main()
