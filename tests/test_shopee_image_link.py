import ast
import io
import logging
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

from PIL import Image, ImageOps

BOT_FILE = Path(__file__).resolve().parents[1] / "bot.py"
TREE = ast.parse(BOT_FILE.read_text(encoding="utf-8"))
HELPERS = [
    node for node in TREE.body
    if isinstance(node, ast.FunctionDef)
    and node.name in {"_shopee_link", "_shopee_public_photo"}
]
NAMESPACE = {"re": re, "logging": logging, "BytesIO": io.BytesIO, "ImageOps": ImageOps}
exec(compile(ast.Module(body=HELPERS, type_ignores=[]), str(BOT_FILE), "exec"), NAMESPACE)
shopee_link = NAMESPACE["_shopee_link"]
public_photo = NAMESPACE["_shopee_public_photo"]


class FakeResponse:
    def __init__(self, data, url, content_type):
        self.data = data
        self.url = url
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, size=-1):
        return self.data[:size] if size >= 0 else self.data


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (400, 400), "white").save(output, format="PNG")
    return output.getvalue()


class ShopeeImageLinkTests(unittest.TestCase):
    def test_accepts_full_product_url(self):
        self.assertEqual(
            shopee_link("https://shopee.com.my/product/29993877/44905654836"),
            "https://shopee.com.my/product/29993877/44905654836",
        )

    def test_accepts_short_share_url_with_query(self):
        link = "https://s.shopee.com.my/qkMYwtxrQ?share_channel_code=1"
        self.assertEqual(shopee_link(link), link)

    def test_rejects_non_shopee_and_non_https_urls(self):
        self.assertEqual(shopee_link("https://example.com/product/1/2"), "")
        self.assertEqual(shopee_link("http://shopee.com.my/product/1/2"), "")
        self.assertEqual(shopee_link("https://shopee.com.my/"), "")

    def test_extracts_public_image_without_product_title(self):
        page = b'<html><meta content="https://cf.shopee.com.my/product.png" property="og:image"></html>'
        responses = [
            FakeResponse(page, "https://shopee.com.my/product/1/2", "text/html; charset=utf-8"),
            FakeResponse(image_bytes(), "https://cf.shopee.com.my/product.png", "image/png"),
        ]
        with patch("urllib.request.urlopen", side_effect=responses):
            with __import__("tempfile").TemporaryDirectory() as folder:
                destination = Path(folder) / "product.jpg"
                self.assertTrue(public_photo(
                    "https://shopee.com.my/product/1/2", destination, "intentionally unrelated words"
                ))
                self.assertTrue(destination.is_file())
                with Image.open(destination) as result:
                    self.assertEqual(result.format, "JPEG")
                    self.assertEqual(result.size, (400, 400))

    def test_short_link_follows_redirect_and_extracts_image(self):
        link = "https://s.shopee.com.my/qkMYwtxrQ?share_channel_code=1"
        page = b'<meta property="og:image" content="https://cf.shopee.com.my/product.png">'
        responses = [
            FakeResponse(page, "https://shopee.com.my/product/1/2", "text/html"),
            FakeResponse(image_bytes(), "https://cf.shopee.com.my/product.png", "image/png"),
        ]
        with patch("urllib.request.urlopen", side_effect=responses):
            with __import__("tempfile").TemporaryDirectory() as folder:
                self.assertTrue(public_photo(link, Path(folder) / "product.jpg", ""))

    def test_rejects_redirect_to_non_shopee_host(self):
        response = FakeResponse(b"<html></html>", "https://example.com/redirected", "text/html")
        with patch("urllib.request.urlopen", return_value=response):
            with __import__("tempfile").TemporaryDirectory() as folder:
                self.assertFalse(public_photo(
                    "https://s.shopee.com.my/qkMYwtxrQ", Path(folder) / "product.jpg", ""
                ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
