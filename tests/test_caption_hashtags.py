"""Regression tests for caption CTA and platform-specific hashtags."""
import unittest

from caption_hashtags import generate_caption


class CaptionHashtagTests(unittest.TestCase):
    def test_shopee_caption_has_clear_cta_and_platform_tag(self):
        caption = generate_caption("Cotton shirt", "fashion", "fashion_women", "Shopee")
        self.assertIn("Cotton shirt", caption)
        self.assertIn("Tekan pautan produk Shopee", caption)
        self.assertIn("#ShopeeMalaysia", caption)

    def test_tiktok_caption_has_clear_cta_and_platform_tag(self):
        caption = generate_caption("Wireless earbuds", "gadget", "gadget_audio", "TikTok")
        self.assertIn("Tekan pautan TikTok Shop", caption)
        self.assertIn("#TikTokMalaysia", caption)

    def test_hashtags_are_unique(self):
        caption = generate_caption("Snack bundle", "food", "food_snacks", "Shopee")
        tags = [word for word in caption.split() if word.startswith("#")]
        self.assertEqual(len(tags), len({tag.casefold() for tag in tags}))


if __name__ == "__main__":
    unittest.main()
