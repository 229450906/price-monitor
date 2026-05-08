from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "product_price_monitor.py"
SPEC = importlib.util.spec_from_file_location("product_price_monitor", MODULE_PATH)
assert SPEC is not None
monitor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(monitor)


class ProductPriceMonitorTests(unittest.TestCase):
    def test_multi_word_query_requires_multiple_terms_by_default(self) -> None:
        raw = "RTX accessory 3,000円" + (" filler" * 800) + "GeForce RTX 5080 195,000円"
        watch = {"name": "RTX 5080", "min_price_jpy": 500, "max_price_jpy": 500000}
        provider = {"condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider)

        self.assertEqual([item["price_jpy"] for item in prices], [195000])

    def test_rtx_5070_ti_does_not_match_plain_5070(self) -> None:
        raw = (
            '<a href="https://auctions.yahoo.co.jp/jp/auction/k1229226568">'
            "ZOTAC GAMING GeForce RTX 5070 SOLID OC"
            "</a>90,000円"
        )
        watch = {"name": "RTX 5070 Ti", "min_price_jpy": 80000, "max_price_jpy": 500000}
        provider = {"name": "Yahoo Auctions", "condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider, "https://auctions.yahoo.co.jp/search/search?p=RTX+5070+Ti")

        self.assertEqual(prices, [])

    def test_rtx_5070_ti_requires_query_sequence(self) -> None:
        raw = (
            '<li class="Product">'
            '<a href="https://auctions.yahoo.co.jp/jp/auction/k1229226568">'
            "ZOTAC GeForce RTX 5070 SOLID GPU RTX 4070 Ti"
            "</a>"
            '<div data-auction-buynowprice="90000"></div>'
            "</li>"
        )
        watch = {"name": "RTX 5070 Ti", "min_price_jpy": 80000, "max_price_jpy": 500000}
        provider = {"name": "Yahoo Auctions", "condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider, "https://auctions.yahoo.co.jp/search/search?p=RTX+5070+Ti")

        self.assertEqual(prices, [])

    def test_yahoo_auction_candidate_uses_item_url(self) -> None:
        raw = (
            '<li class="Product">'
            '<a href="https://auctions.yahoo.co.jp/jp/auction/v1228825746">'
            "ZOTAC GAMING GeForce RTX 5070 Ti SOLID"
            "</a>"
            '<div data-auction-buynowprice="140000"></div>'
            "</li>"
        )
        watch = {"name": "RTX 5070 Ti", "min_price_jpy": 80000, "max_price_jpy": 500000}
        provider = {"name": "Yahoo Auctions", "condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider, "https://auctions.yahoo.co.jp/search/search?p=RTX+5070+Ti")

        self.assertEqual(prices[0]["price_jpy"], 140000)
        self.assertEqual(prices[0]["url"], "https://auctions.yahoo.co.jp/jp/auction/v1228825746")

    def test_yahoo_auction_candidate_requires_item_url(self) -> None:
        raw = '<li class="Product">ZOTAC GAMING GeForce RTX 5070 Ti SOLID 140,000円</li>'
        watch = {"name": "RTX 5070 Ti", "min_price_jpy": 80000, "max_price_jpy": 500000}
        provider = {"name": "Yahoo Auctions", "condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider, "https://auctions.yahoo.co.jp/search/search?p=RTX+5070+Ti")

        self.assertEqual(prices, [])

    def test_yahoo_auction_ignores_current_bid_without_buy_now(self) -> None:
        raw = (
            '<li class="Product">'
            '<a href="https://auctions.yahoo.co.jp/jp/auction/v1228825746">'
            "ASUS PRIME GeForce RTX 5070 Ti 16GB"
            "</a>"
            '<span class="Product__label">現在</span>'
            '<span class="Product__priceValue u-textRed">140,000円</span>'
            "</li>"
        )
        watch = {"name": "RTX 5070 Ti", "min_price_jpy": 80000, "max_price_jpy": 500000}
        provider = {"name": "Yahoo Auctions", "condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider, "https://auctions.yahoo.co.jp/search/search?p=RTX+5070+Ti")

        self.assertEqual(prices, [])

    def test_yahoo_auction_prefers_buy_now_price_over_current_bid(self) -> None:
        raw = (
            '<li class="Product">'
            '<a href="https://auctions.yahoo.co.jp/jp/auction/v1228825746">'
            "ASUS PRIME GeForce RTX 5070 Ti 16GB"
            "</a>"
            '<span class="Product__label">現在</span>'
            '<span class="Product__priceValue u-textRed">140,000円</span>'
            '<span class="Product__label">即決</span>'
            '<span class="Product__priceValue">150,000円</span>'
            "</li>"
        )
        watch = {"name": "RTX 5070 Ti", "min_price_jpy": 80000, "max_price_jpy": 500000}
        provider = {"name": "Yahoo Auctions", "condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider, "https://auctions.yahoo.co.jp/search/search?p=RTX+5070+Ti")

        self.assertEqual([item["price_jpy"] for item in prices], [150000])

    def test_yahoo_auction_prefers_displayed_buy_now_over_hidden_price(self) -> None:
        raw = (
            '<li class="Product">'
            '<a href="https://auctions.yahoo.co.jp/jp/auction/q1225976613">'
            "PNY GeForce RTX 5070 Ti 16GB"
            "</a>"
            '<div data-auction-buynowprice="158364"></div>'
            '<span class="Product__label">現在</span>'
            '<span class="Product__priceValue u-textRed">174,200円</span>'
            '<span class="Product__label">即決</span>'
            '<span class="Product__priceValue">174,200円</span>'
            "</li>"
        )
        watch = {"name": "RTX 5070 Ti", "min_price_jpy": 80000, "max_price_jpy": 500000}
        provider = {"name": "Yahoo Auctions", "condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider, "https://auctions.yahoo.co.jp/search/search?p=RTX+5070+Ti")

        self.assertEqual([item["price_jpy"] for item in prices], [174200])

    def test_min_price_filters_low_page_noise(self) -> None:
        raw = "GeForce RTX 5080 3,980円" + (" filler" * 800) + "GeForce RTX 5080 195,000円"
        watch = {"name": "RTX 5080", "min_price_jpy": 120000, "max_price_jpy": 500000}
        provider = {"condition": "used", "source_type": "auction"}

        prices = monitor.extract_prices(raw, watch, provider)

        self.assertEqual([item["price_jpy"] for item in prices], [195000])

    def test_markdown_cells_escape_table_pipes(self) -> None:
        self.assertEqual(monitor.md_cell("a|b\nc"), "a\\|b c")


if __name__ == "__main__":
    unittest.main()
