"""Manual live smoke test for public image extraction from Shopee links."""
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
        for index, link in enumerate(LINKS, start=1):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as folder:
                destination = Path(folder) / f"product-{index}.jpg"
                success = public_photo(link, destination, "")
                self.assertTrue(
                    success and destination.is_file(),
                    f"Could not extract a public product image from link #{index}: {link}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
