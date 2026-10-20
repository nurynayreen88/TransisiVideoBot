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
        self.assertTrue(all("AUDIO:" in prompt for prompt in prompts))

    def test_category_specific_sfx(self):
        prompt = prompt_engine._creative_variation("fashion", "children's outfit", 0)
        self.assertIn("fabric swish", prompt)

    def test_20_seconds_single_option_stays_one_full_prompt(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Designer Kid Bed", "bright bedroom", "push",
            duration=20, product_type="home", split=False
        )
        self.assertIn("exactly 20 seconds", prompt)
        self.assertNotIn("=== KLIPPO PART 2 ===", prompt)

    def test_30_seconds_single_option_stays_one_full_prompt(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Designer Kid Bed", "bright bedroom", "push",
            duration=30, product_type="home", split=False
        )
        self.assertIn("exactly 30 seconds", prompt)
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

    def test_bed_storyboard_uses_furniture_specific_beats(self):
        scenes = prompt_engine._category_specific_scenes("home", "Designer Kid Bed")
        text = " ".join(shot + " " + direction for shot, direction in scenes)
        self.assertIn("FULL BED REVEAL", text)
        self.assertIn("structural details", text)
        self.assertIn("do not demonstrate unsupported storage", text)
        self.assertEqual(len(scenes), 5)

    def test_cookware_set_storyboard_shows_set_and_plausible_use(self):
        scenes = prompt_engine._category_specific_scenes(
            "kitchen", "Tefal Quickchef 7PCS cookware set"
        )
        text = " ".join(shot + " " + direction for shot, direction in scenes)
        self.assertIn("COMPLETE SET", text)
        self.assertIn("physically plausible kitchen action", text)
        self.assertIn("do not add pieces", text)
        self.assertIn("invented savings", text)

    def test_category_storyboard_varies_for_fashion_and_gadgets(self):
        fashion = " ".join(x[0] + " " + x[1] for x in prompt_engine._category_specific_scenes(
            "fashion", "children's T-shirt and skorts"
        ))
        gadget = " ".join(x[0] + " " + x[1] for x in prompt_engine._category_specific_scenes(
            "gadget", "wireless earbuds"
        ))
        self.assertIn("FABRIC / DESIGN DETAIL", fashion)
        self.assertIn("VISIBLE CONTROL / PORT", gadget)
        self.assertNotEqual(fashion, gadget)

    def test_30_second_single_prompt_has_five_category_specific_timed_scenes(self):
        prompt = prompt_engine.build_prompt(
            "storyboard", "Tefal Quickchef 7PCS cookware set", "bright kitchen", "push",
            style="auto", duration=30, product_type="kitchen", split=False
        )
        self.assertIn("exactly 30 seconds", prompt)
        self.assertIn("Each scene lasts exactly 6 seconds", prompt)
        self.assertIn("PRACTICAL DETAIL / VALUE", prompt)
        self.assertNotIn("=== KLIPPO PART 2 ===", prompt)

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

    def test_standard_prompt_uses_default_malay_without_undefined_state(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Cotton shirt", "studio", "push", duration=10
        )
        self.assertIn("in Bahasa Melayu Malaysia", prompt)

    def test_standard_prompt_honours_english_language_choice(self):
        prompt = prompt_engine.build_prompt(
            "standard", "Cotton shirt", "studio", "push",
            duration=10, prompt_language="English"
        )
        self.assertIn("in English", prompt)


if __name__ == "__main__":
    unittest.main()