import csv
import json
import tempfile
import unittest
from pathlib import Path

from web_scraper import (
    AccessBlockedError,
    ScraperEngine,
    ScraperError,
    save_csv,
    save_json,
)


class TestWebScraper(unittest.TestCase):
    def test_parse_product(self):
        html = """
        <html>
          <head><title>Fallback Title</title></head>
          <body>
            <h1 class="product-title">Example Product</h1>
            <span class="price">$25</span>
            <div class="description">Useful item</div>
          </body>
        </html>
        """
        result = ScraperEngine.parse_product(html, "https://example.test/product")
        self.assertEqual(result.title, "Example Product")
        self.assertEqual(result.price, "$25")
        self.assertEqual(result.description, "Useful item")

    def test_fallback_selectors(self):
        html = """
        <html>
          <head><title>Fallback Product</title></head>
          <body>
            <h1>Fallback Product</h1>
            <span itemprop="price">$30</span>
            <p itemprop="description">Fallback description</p>
          </body>
        </html>
        """
        result = ScraperEngine.parse_product(html, "https://example.test")
        self.assertEqual(result.title, "Fallback Product")
        self.assertEqual(result.price, "$30")

    def test_block_detection(self):
        html = "<html><body>Please complete CAPTCHA to continue.</body></html>"
        self.assertTrue(ScraperEngine._looks_blocked(html))

        with self.assertRaises(AccessBlockedError):
            raise AccessBlockedError("blocked")

    def test_missing_title(self):
        html = "<html><body><p>No product title</p></body></html>"
        with self.assertRaises(ScraperError):
            ScraperEngine.parse_product(html, "https://example.test")

    def test_json_and_csv_outputs(self):
        html = """
        <h1 class="product-title">Test</h1>
        <span class="price">$5</span>
        """
        record = ScraperEngine.parse_product(html, "https://example.test")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_file = root / "out.json"
            csv_file = root / "out.csv"

            save_json([record], json_file)
            save_csv([record], csv_file)

            data = json.loads(json_file.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["title"], "Test")

            with csv_file.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["title"], "Test")


if __name__ == "__main__":
    unittest.main()
