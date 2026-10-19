"""Offline tests for duration-specific product video prompts."""
import unittest

from modules.product_video_prompt import build_video_prompts


class ProductVideoPromptTests(unittest.TestCase):
    def test_duration_returns_one_prompt_per_ten_seconds(self):
        for duration, expected in ((10, 1), (20, 2), (30, 3)):
            with self.subTest(duration=duration):
                prompts = build_video_prompts(duration)
                self.assertEqual(len(prompts), expected)
                self.assertTrue(all("exactly 10 seconds" in p for p in prompts))

    def test_ring_scale_and_malaysian_voice_rules_are_explicit(self):
        prompt = build_video_prompts(10)[0].lower()
        self.assertIn("ring must remain small enough", prompt)
        self.assertIn("table-sized", prompt)
        self.assertIn("bahasa melayu malaysia", prompt)
        self.assertIn("indonesian voice", prompt)
        self.assertIn("no on-screen text", prompt)
        self.assertIn("CATEGORY-SPECIFIC SCENE AND ACTION LOGIC", prompt)
        self.assertEqual(prompt.count("Open immediately with a product-specific visual hook."), 1)

    def test_longer_durations_have_different_story_progression(self):
        ten = build_video_prompts(10)[0]
        twenty = build_video_prompts(20)
        thirty = build_video_prompts(30)
        self.assertIn("HOOK + HERO", ten)
        self.assertIn("HOOK + INTRODUCTION", twenty[0])
        self.assertIn("DEMONSTRATION + CTA", twenty[1])
        self.assertIn("HOOK + SITUATION", thirty[0])
        self.assertIn("DEMONSTRATION + BENEFIT", thirty[1])
        self.assertIn("DETAIL + CTA", thirty[2])

    def test_invalid_duration_is_rejected(self):
        with self.assertRaises(ValueError):
            build_video_prompts(15)


if __name__ == "__main__":
    unittest.main()
