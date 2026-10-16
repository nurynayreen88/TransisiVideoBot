"""Regression tests for curated, fixed storyboard prompt templates."""
import unittest

from prompt_library import build_curated_storyboard


class CuratedPromptLibraryTests(unittest.TestCase):
    def test_luxury_prompt_has_no_empty_metadata_placeholders(self):
        prompt = build_curated_storyboard(
            "The product shown in the uploaded reference image.\n\nVERIFIED IMAGE OBSERVATIONS:\nNAMA_PRODUK: TIDAK PASTI\nKATEGORI: TIDAK PASTI",
            style="luxury",
        )
        self.assertIn("💎 Luxury Product", prompt)
        self.assertIn("NO ON-SCREEN HOOK TEXT", prompt)
        self.assertNotIn("Visible observations:", prompt)
        self.assertNotIn("Optional user details:", prompt)
        self.assertNotIn("NAMA_PRODUK is", prompt)
        self.assertNotIn("CIRI_VISUAL lists", prompt)

    def test_luxury_prompt_uses_saved_fixed_wording(self):
        prompt = build_curated_storyboard(
            "The product shown in the uploaded reference image.",
            style="luxury",
        )
        self.assertIn("Refined luxury product cinematography", prompt)
        self.assertIn("soft rim highlights", prompt)
        self.assertIn("No on-screen text, captions, icons or decorative graphics unless explicitly requested", prompt)

    def test_twenty_seconds_returns_two_copyable_ten_second_prompts(self):
        prompt = build_curated_storyboard(
            "The product shown in the uploaded reference image.",
            style="luxury",
            duration=20,
        )
        self.assertIn("EXACT DURATION: 10 seconds", prompt)
        self.assertEqual(prompt.count("EXACT DURATION: 10 seconds"), 2)
        self.assertIn("=== KLIPPO PART 2 ===", prompt)
        self.assertIn("exact final held frame of Part 1", prompt)

    def test_user_scene_is_used_without_rewriting_template(self):
        prompt = build_curated_storyboard(
            "The product shown in the uploaded reference image.",
            style="luxury",
            scene="a warm beige studio background",
        )
        self.assertIn("SETTING: a warm beige studio background", prompt)
        self.assertIn("Refined luxury product cinematography", prompt)

    def test_white_doodle_is_graphic_only_not_auto_text(self):
        prompt = build_curated_storyboard(
            "The product shown in the uploaded reference image.",
            style="white_doodle",
        )
        self.assertIn("White doodle graphics are explicitly requested", prompt)
        self.assertIn("Do not invent words, claims, prices or captions", prompt)


if __name__ == "__main__":
    unittest.main()
