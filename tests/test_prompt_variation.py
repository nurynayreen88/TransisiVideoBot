"""Regression tests for connected Klippo prompts and creative variation."""
import unittest
import prompt_engine


class CreativeVariationTests(unittest.TestCase):
    def setUp(self):
        prompt_engine._RECENT_CREATIVE_CHOICES.clear()

    def test_fashion_actions_vary_across_three_generations(self):
        prompts = [
            prompt_engine._creative_variation(
                "fashion", "Babyshop Disney children's T-shirt and skorts", 0
            )
            for _ in range(3)
        ]
        self.assertEqual(len(set(prompts)), 3)
        self.assertTrue(all("AUDIO / SFX:" in prompt for prompt in prompts))

    def test_category_specific_sfx(self):
        prompt = prompt_engine._creative_variation("fashion", "children's outfit", 0)
        self.assertIn("fabric swish", prompt)

    def test_20_seconds_single_option_stays_one_full_prompt(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Designer Kid Bed", "bright bedroom", "push",
            duration=20, product_type="home", split=False
        )
        self.assertIn("OUTPUT: 20 seconds", prompt)
        self.assertNotIn("=== KLIPPO PART 2 ===", prompt)

    def test_30_seconds_single_option_stays_one_full_prompt(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Designer Kid Bed", "bright bedroom", "push",
            duration=30, product_type="home", split=False
        )
        self.assertIn("OUTPUT: 30 seconds", prompt)
        self.assertNotIn("=== KLIPPO PART 2 ===", prompt)

    def test_20_seconds_produces_two_connected_ten_second_prompts(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Babyshop children's outfit", "bright studio", "push",
            duration=20, product_type="fashion"
        )
        self.assertIn("=== KLIPPO PART 2 ===", prompt)
        self.assertEqual(prompt.count("OUTPUT: 10 seconds"), 2)
        self.assertIn("PART 2:", prompt)

    def test_30_seconds_produces_three_connected_ten_second_prompts(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Babyshop children's outfit", "bright studio", "push",
            duration=30, product_type="fashion"
        )
        self.assertIn("=== KLIPPO PART 2 ===", prompt)
        self.assertIn("=== KLIPPO PART 3 ===", prompt)
        self.assertEqual(prompt.count("OUTPUT: 10 seconds"), 3)
        self.assertIn("PART 3:", prompt)
        self.assertIn("Part 2's final frame", prompt)

    def test_all_variations_include_audio_limitation(self):
        prompt = prompt_engine._creative_variation("other", "desk organiser", 0)
        self.assertIn("never stack effects", prompt)
        self.assertIn("cannot create audio", prompt)

    def test_ad_angle_instructions_are_distinct_and_non_generic(self):
        keys = ("question", "reveal", "demo", "relatable", "premium", "affiliate")
        instructions = [prompt_engine.creative_angle_instruction(key) for key in keys]
        self.assertEqual(len(set(instructions)), len(keys))
        self.assertTrue(all(instructions))
        self.assertEqual(prompt_engine.creative_angle_instruction("auto"), "")
        self.assertIn("verified details", prompt_engine.creative_angle_instruction("affiliate"))
        self.assertIn("physically plausible", prompt_engine.creative_angle_instruction("demo"))


if __name__ == "__main__":
    unittest.main()