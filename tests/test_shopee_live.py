"""Live smoke tests: verify the two user-provided Shopee links can yield an image."""
import ast
import io
import logging
import re
import tempfile
import unittest
from pathlib import Path

from PIL import ImageOps

BOT_FILE = Path(__file__).resolve().parents[1] / "bot.py"
TREE = ast.parse(BOT_FILE.read_text(encoding="utf-8"))
HELPERS = [
    node for node in TREE.body
    if isinstance(node, ast.FunctionDef)
    and node.name in {"_shopee_link", "_shopee_public_photo"}
]
NAMESPACE = {"re": re, "logging": logging, "BytesIO": io.BytesIO, "ImageOps": ImageOps}
exec(compile(ast.Module(body=HELPERS, type_ignores=[]), str(BOT_FILE), "exec"), NAMESPACE)
public_photo = NAMESPACE["_shopee_public_photo"]

LINKS = (
    "https://shopee.com.my/product/29993877/44905654836",
    "https://s.shopee.com.my/qkMYwtxrQ?share_channel_code=1",
)


class LiveShopeeLinkTests(unittest.TestCase):
    def test_user_supplied_links_can_yield_public_product_images(self):
        # A real network smoke test, run in GitHub Actions (not mocked).
        for index, link in enumerate(LINKS, start=1):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as folder:
                destination = Path(folder) / f"product-{index}.jpg"
                success = public_photo(link, destination, "")
                if not (success and destination.is_file()):
                    from urllib.request import Request, urlopen
                    from urllib.parse import urlparse
                    try:
                        request = Request(link, headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                            "Accept-Language": "en-MY,en;q=0.9,ms;q=0.8",
                        })
                        with urlopen(request, timeout=15) as response:
                            page = response.read(12000).decode("utf-8", "replace")
                            print(f"DIAGNOSTIC link #{index}: status={response.status}, final_url={response.geturl()}, content_type={response.headers.get('Content-Type')}, page_start={page[:1800]!r}")
                    except Exception as error:
                        print(f"DIAGNOSTIC link #{index}: request_error={type(error).__name__}: {error}")
                self.assertTrue(
                    success and destination.is_file(),
                    f"Could not extract a public product image from link #{index}: {link}",
                )
                self.assertGreater(destination.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
