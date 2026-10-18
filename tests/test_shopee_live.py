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
                            page = response.read(500000).decode("utf-8", "replace")
                            print("DIAG_COUNTS", len(page), page.count("susercontent"), page.count("44905654836"))
                            print("DIAG_META", [line[:500] for line in page.splitlines() if "<meta" in line.lower() and ("image" in line.lower())][:10])
                            print("DIAG_IMAGE_URLS", re.findall("https?[^\\\"']+susercontent[^\\\"']+", page)[:8])
                            print(f"DIAGNOSTIC link #{index}: status={response.status}, final_url={response.geturl()}, content_type={response.headers.get('Content-Type')}, page_start={page[:1800]!r}")
                    except Exception as error:
                        print(f"DIAGNOSTIC link #{index}: request_error={type(error).__name__}: {error}")
                    proxy_url = "https://r.jina.ai/http://shopee.com.my/product/29993877/44905654836"
                    try:
                        proxy_req = Request(proxy_url, headers={"Accept": "text/plain", "User-Agent": "Mozilla/5.0"})
                        with urlopen(proxy_req, timeout=20) as proxy_response:
                            proxy_body = proxy_response.read(30000).decode("utf-8", "replace")
                            print(f"DIAGNOSTIC JINA status={proxy_response.status}, body={proxy_body[:6000]!r}")
                    except Exception as proxy_error:
                        print(f"DIAGNOSTIC JINA {type(proxy_error).__name__}: {proxy_error}")
                    for api_url in (
                        "https://shopee.com.my/api/v4/pdp/get_pc?shop_id=29993877&item_id=44905654836",
                        "https://shopee.com.my/api/v4/item/get?shopid=29993877&itemid=44905654836",
                    ):
                        try:
                            api_req = Request(api_url, headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                                "Accept": "application/json",
                                "Referer": "https://shopee.com.my/product/29993877/44905654836",
                                "x-api-source": "pc",
                            })
                            with urlopen(api_req, timeout=12) as api_response:
                                body = api_response.read(10000).decode("utf-8", "replace")
                                print(f"DIAGNOSTIC API {api_url}: status={api_response.status}, type={api_response.headers.get('Content-Type')}, body={body[:2500]!r}")
                        except Exception as api_error:
                            print(f"DIAGNOSTIC API {api_url}: {type(api_error).__name__}: {api_error}")
                self.assertTrue(
                    success and destination.is_file(),
                    f"Could not extract a public product image from link #{index}: {link}",
                )
                self.assertGreater(destination.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
