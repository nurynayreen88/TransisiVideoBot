"""Regression checks for Klippo action/SFX variation."""
import unittest
import prompt_engine


class CreativeVariationTests(unittest.TestCase):
    def setUp(self):
        prompt_engine._RECENT_CREATIVE_CHOICES.clear()

    def test_fashion_actions_vary_across_three_generations(self):
        results = [
            prompt_engine._creative_variation(
                "fashion", "Babyshop Disney children's T-shirt and skorts", 0
            )
            for _ in range(3)
        ]
        self.assertEqual(len(set(results)), 3)
        self.assertTrue(all("AUDIO / SFX:" in item for item in results))

    def test_sfx_matches_category(self):
        prompt_engine._RECENT_CREATIVE_CHOICES.clear()
        text = prompt_engine._creative_variation("fashion", "children's outfit", 0)
        self.assertIn("fabric swish", text)

    def test_continuation_keeps_part_two_context(self):
        text = prompt_engine._creative_variation("fashion", "children's outfit", 2)
        self.assertIn("CONTINUATION ACTION", text)
        self.assertIn("immediately previous part's final-frame identity", text)

    def test_20_seconds_returns_two_connected_10_second_parts(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Babyshop children's outfit", "bright studio", "push",
            duration=20, product_type="fashion"
        )
        self.assertIn("=== KLIPPO PART 2 ===", prompt)
        self.assertEqual(prompt.count("OUTPUT: 10 seconds"), 2)
        self.assertIn("SECOND CLIP 10s", prompt)

    def test_30_seconds_returns_three_connected_10_second_parts(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Babyshop children's outfit", "bright studio", "push",
            duration=30, product_type="fashion"
        )
        self.assertIn("=== KLIPPO PART 2 ===", prompt)
        self.assertIn("=== KLIPPO PART 3 ===", prompt)
        self.assertEqual(prompt.count("OUTPUT: 10 seconds"), 3)
        self.assertIn("THIRD CLIP 10s", prompt)
        self.assertIn("final frame from Part 2", prompt)

    def test_general_products_get_subtle_sfx(self):
        text = prompt_engine._creative_variation("other", "desk organiser", 0)
        self.assertIn("soft chime", text)
        self.assertIn("never stack effects", text)


if __name__ == "__main__":
    unittest.main()
