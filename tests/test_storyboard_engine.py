"""Offline tests for the no-API four-panel storyboard prompt builder."""
import unittest
from modules.storyboard_engine import build_storyboard_prompt


class StoryboardPromptTests(unittest.TestCase):
    def test_prompt_contains_four_detailed_panels_and_vertical_layout(self):
        prompt = build_storyboard_prompt("shopee", "model_holding", "cafe")
        self.assertIn("Shopee Affiliate", prompt)
        self.assertIn("adult model naturally holding or wearing", prompt)
        self.assertIn("modern stylish cafe", prompt)
        self.assertIn("EXACTLY FOUR", prompt)
        self.assertIn("9:16 vertical storyboard sheet", prompt)
        self.assertIn("PANEL 1 — HOOK", prompt)
        self.assertIn("PANEL 2 — PRODUCT FORM", prompt)
        self.assertIn("PANEL 3 — DETAIL", prompt)
        self.assertIn("PANEL 4 — FINAL HERO", prompt)
        self.assertIn("original visible logo", prompt)

    def test_tiktok_and_product_only(self):
        prompt = build_storyboard_prompt("tiktok", "product_only", "studio")
        self.assertIn("TikTok Viral", prompt)
        self.assertIn("do not include a model, hands", prompt)
        self.assertIn("premium minimalist studio", prompt)

    def test_user_supplied_attributes_are_included(self):
        prompt = build_storyboard_prompt(
            "shopee", "product_only", "home",
            {"product_type": "handbag", "colors": "black leather", "visible_details": "gold zipper"},
        )
        self.assertIn("handbag", prompt)
        self.assertIn("black leather", prompt)
        self.assertIn("gold zipper", prompt)

    def test_unknown_options_fall_back_safely(self):
        prompt = build_storyboard_prompt("unknown", "unknown", "unknown")
        self.assertIn("Shopee Affiliate", prompt)
        self.assertIn("Product-only campaign", prompt)
        self.assertIn("premium minimalist studio", prompt)


if __name__ == "__main__":
    unittest.main()
