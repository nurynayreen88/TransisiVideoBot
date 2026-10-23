"""Diagnostic only: inspect browser-rendered Shopee product image URLs.

This script does not log in, bypass CAPTCHA, or download product data. It prints
only URL host/path samples to avoid leaking tracking query strings.
"""
import re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

LINKS = (
    "https://shopee.com.my/product/29993877/44905654836",
    "https://s.shopee.com.my/qkMYwtxrQ?share_channel_code=1",
)

def safe_url(value):
    try:
        parsed = urlparse(value)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme and parsed.netloc else ""
    except Exception:
        return ""

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1365, "height": 900},
            locale="en-MY",
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        )
        page = context.new_page()
        for index, link in enumerate(LINKS, start=1):
            print(f"\nLINK #{index}: {safe_url(link)}")
            try:
                response = page.goto(link, wait_until="domcontentloaded", timeout=45000)
                print("NAV_STATUS:", response.status if response else "no-main-response")
                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass
                page.wait_for_timeout(5000)
                print("FINAL_URL:", safe_url(page.url))
                print("TITLE:", (page.title() or "")[:120])
                print("BODY_TEXT:", re.sub(r"\\s+", " ", page.locator("body").inner_text(timeout=5000))[:300])
                data = page.evaluate("""() => {
                    const urls = new Set();
                    for (const el of document.querySelectorAll('img')) {
                      if (el.currentSrc) urls.add(el.currentSrc);
                      if (el.src) urls.add(el.src);
                      for (const v of (el.getAttribute('srcset') || '').split(',')) {
                        const u = v.trim().split(/\\s+/)[0]; if (u.startsWith('http')) urls.add(u);
                      }
                    }
                    for (const el of document.querySelectorAll('[style*="background"]')) {
                      const s = getComputedStyle(el).backgroundImage;
                      for (const m of s.matchAll(/url\\(["']?(.*?)["']?\\)/g)) if (m[1].startsWith('http')) urls.add(m[1]);
                    }
                    return {imgCount: document.images.length, urls: [...urls]};
                }""")
                print("DOM_IMG_COUNT:", data["imgCount"])
                candidates = []
                for value in data["urls"]:
                    parsed = urlparse(value)
                    host = (parsed.hostname or "").lower()
                    if any(x in host for x in ("susercontent.com", "shopeeusercontent.com", "shopeemobile.com")):
                        candidates.append(safe_url(value))
                print("SHOPEE_IMAGE_URL_COUNT:", len(set(candidates)))
                for value in list(dict.fromkeys(candidates))[:12]:
                    print("IMAGE_CANDIDATE:", value)
            except Exception as exc:
                print("BROWSER_ERROR:", type(exc).__name__, str(exc)[:250])
        browser.close()

if __name__ == "__main__":
    main()
