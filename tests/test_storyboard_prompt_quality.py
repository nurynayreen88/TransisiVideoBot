"""Regression checks for storyboard prompt quality and mode consistency."""
import unittest

from prompt_engine import build_prompt
from smart_prompt_engine import choose_variation


class StoryboardPromptQualityTests(unittest.TestCase):
    def test_luxury_style_does_not_add_white_doodles_when_hook_unknown(self):
        prompt = build_prompt(
            "storyboard",
            "PRODUCT REFERENCE: the product in the uploaded reference image. Visible observations: unavailable.",
            "clean premium studio background, selected to complement the exact product reference",
            "push",
            style="luxury",
            duration=10,
        )
        self.assertIn("NO ON-SCREEN HOOK TEXT", prompt)
        self.assertIn("do not add headline text or decorative doodles", prompt)
        self.assertNotIn("decorative white doodle only", prompt)

    def test_internal_evidence_placeholders_are_not_emitted(self):
        prompt = build_prompt(
            "storyboard",
            "PRODUCT REFERENCE: uploaded product image; details not verified.",
            "clean premium studio background, selected to complement the exact product reference",
            "push",
            style="luxury",
            duration=10,
        )
        self.assertNotIn("NAMA_PRODUK is", prompt)
        self.assertNotIn("TEKS_DISAHKAN", prompt)
        self.assertNotIn("CIRI_BERTULIS", prompt)
        self.assertNotIn("CIRI_VISUAL lists", prompt)

    def test_luxury_variations_stay_premium(self):
        for seed in range(20):
            variation = choose_variation(
                "KATEGORI: beg",
                "clean premium studio background, selected to complement the exact product reference",
                "push",
                style="luxury",
                seed=seed,
            )
            self.assertIn(variation["setting"], (
                "a dark charcoal luxury set with restrained warm rim lighting and a realistic grounded surface",
                "a deep espresso studio with soft amber highlights and no distracting props",
                "a refined midnight-toned set with controlled reflections and natural material response",
            ))
            self.assertIn(variation["mood"], (
                "polished premium commercial, restrained and elegant",
                "editorial product film with clean composition and tactile detail",
            ))


if __name__ == "__main__":
    unittest.main()
