"""Offline tests for the single-image storyboard prompt engine."""
import os
import unittest
from unittest import mock

from modules.storyboard_engine import (
    StoryboardEngineError,
    build_storyboard_prompt,
    image_api_enabled,
    generate_storyboard_image,
)


class StoryboardPromptTests(unittest.TestCase):
    def test_prompt_contains_goal_style_background_and_single_image_lock(self):
        prompt = build_storyboard_prompt("shopee", "model_holding", "cafe")
        self.assertIn("Shopee Affiliate", prompt)
        self.assertIn("model naturally holding or wearing", prompt)
        self.assertIn("modern cafe", prompt)
        self.assertIn("NOT a multi-panel storyboard", prompt)
        self.assertIn("vertical 9:16", prompt)
        self.assertIn("original logo", prompt)

    def test_tiktok_goal_and_product_only_style(self):
        prompt = build_storyboard_prompt("tiktok", "product_only", "studio")
        self.assertIn("TikTok Viral", prompt)
        self.assertIn("no people, hands", prompt)
        self.assertIn("premium minimalist studio", prompt)

    def test_attributes_are_included_only_when_supplied(self):
        prompt = build_storyboard_prompt(
            "shopee", "product_only", "home",
            {"product_type": "handbag", "colors": "black leather", "visible_details": "gold zipper"},
        )
        self.assertIn("handbag", prompt)
        self.assertIn("black leather", prompt)
        self.assertIn("gold zipper", prompt)

    def test_api_is_disabled_by_default_and_generation_is_guarded(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(image_api_enabled())
            with self.assertRaises(StoryboardEngineError):
                generate_storyboard_image(b"not-an-image", "prompt")

    def test_api_requires_explicit_opt_in(self):
        with mock.patch.dict(os.environ, {"KLIPPO_ENABLE_GEMINI_IMAGE_API": "true"}, clear=True):
            self.assertTrue(image_api_enabled())
            with self.assertRaises(StoryboardEngineError):
                generate_storyboard_image(b"not-an-image", "prompt")


if __name__ == "__main__":
    unittest.main()
