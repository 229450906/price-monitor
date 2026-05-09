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

    def test_goofish_reference_filters_accessories_and_3s(self) -> None:
        payload = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "id": "1001",
                            "categoryId": "50025382",
                            "title": "Meta Quest 3S 128G 国行",
                            "price": "2600",
                            "city": "上海",
                        }
                    },
                    {
                        "data": {
                            "id": "1002",
                            "categoryId": "50025382",
                            "title": "Quest3 128G 头带 配件",
                            "price": "120",
                            "city": "杭州",
                        }
                    },
                    {
                        "data": {
                            "id": "1003",
                            "categoryId": "50025382",
                            "title": "Meta Quest 3 128G 成色好",
                            "price": "3200",
                            "city": "东京",
                        }
                    },
                ]
            },
        }
        watch = {
            "name": "Meta Quest 3",
            "china_reference_terms": ["meta", "quest", "3"],
            "china_reference_min_price_cny": 500,
            "china_reference_require_query_sequence": False,
            "exclude_terms": ["quest 3s"],
            "accessory_terms": ["头带", "配件"],
        }
        reference = monitor.DEFAULT_CHINA_REFERENCE

        candidates = monitor.extract_goofish_reference_candidates(payload, watch, reference)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["reference_price_cny"], 3200)
        self.assertEqual(candidates[0]["reference_url"], "https://www.goofish.com/item?id=1003&categoryId=50025382")

    def test_alert_includes_china_reference(self) -> None:
        message = monitor.format_alert(
            [
                {
                    "watch_name": "RTX 5080",
                    "provider": "Yahoo Auctions",
                    "source_type": "auction",
                    "condition": "used",
                    "price_jpy": 192000,
                    "target_price_jpy": None,
                    "hit_reason": "new low",
                    "url": "https://auctions.yahoo.co.jp/jp/auction/example",
                    "reference_provider": "Goofish",
                    "reference_price_cny": 6200,
                    "reference_title": "RTX 5080 显卡",
                    "reference_url": "https://www.goofish.com/item?id=abc&categoryId=0",
                    "snippet": "sample",
                }
            ]
        )

        self.assertIn("China Ref: 6,200 CNY via Goofish / RTX 5080 显卡", message)
        self.assertIn("China Ref URL: https://www.goofish.com/item?id=abc&categoryId=0", message)


if __name__ == "__main__":
    unittest.main()
