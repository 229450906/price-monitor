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
