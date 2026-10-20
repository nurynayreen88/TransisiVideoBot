import json
import tempfile
import unittest
from pathlib import Path

import prompt_catalog
from prompt_catalog import opening_direction, product_hook
from prompt_engine import (
    UNIVERSAL_PROMPT_FRAMEWORKS,
    _prompt_sentence,
    _resolve_auto_style,
    build_prompt,
)


class PromptQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = prompt_catalog.DB_PATH
        prompt_catalog.DB_PATH = Path(self.temp_dir.name) / "test_prompt_catalog.sqlite3"

    def tearDown(self):
        prompt_catalog.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_sentence_summary_preserves_short_multi_sentence_constraints(self):
        source = "Natural everyday-carry scene focused on the wallet itself. No capacity, durability or security claims."
        result = _prompt_sentence(source, 180)
        self.assertEqual(result, source)
        self.assertIn("No capacity, durability or security claims.", result)

    def test_long_first_sentence_is_not_cut_mid_sentence(self):
        source = "Premium commercial presentation with careful framing, soft directional light and a controlled camera move that preserves the exact visible product. Do not invent materials."
        result = _prompt_sentence(source, 70)
        self.assertTrue(result.endswith("."))
        self.assertIn("preserves the exact visible product.", result)
        self.assertNotIn("Do not invent materials.", result)  # exceeds target after the complete first sentence

    def test_english_opening_direction_does_not_force_malay_speech(self):
        direction = opening_direction("bag", "English")
        self.assertIn("If voiceover is used, speak clear English.", direction)
        self.assertNotIn("Bahasa Melayu Malaysia", direction)

    def test_english_product_hook_uses_english_not_malay(self):
        for description in ("NAMA_PRODUK: Bonia handbag", "KATEGORI: handbag"):
            hooks = [product_hook(description, "English") for _ in range(30)]
            result = next((hook for hook in hooks if hook), None)
            self.assertIsNotNone(result)
            self.assertTrue(any(word in result.lower() for word in ("looking", "comparing", "interested", "closer look")))
            self.assertNotIn("boleh tengok", result.lower())

    def test_auto_bag_style_does_not_choose_wallet_style_for_handbag(self):
        allowed = {
            "handbag_showcase", "bag_daily_carry", "bag_tabletop_reveal",
            "sling_bag_lifestyle", "bag_detail_macro", "bag_flatlay",
        }
        for _ in range(20):
            self.assertIn(_resolve_auto_style("auto", "bag", "Bonia handbag"), allowed)

    def test_white_doodle_first_clip_holds_final_frame_for_continuity(self):
        prompt = build_prompt(
            mode="storyboard",
            product="PRODUCT NAME: unknown. Optional user details:",
            scene="clean premium studio background",
            motion="push",
            style="white_doodle",
            duration=20,
        )
        first_part = prompt.split("=== KLIPPO PART 2 ===", 1)[0]
        self.assertIn("HOLD the final frame", first_part, first_part)

    def test_universal_framework_keys_resolve_to_canonical_catalog_styles(self):
        canonical = set(prompt_catalog.STYLES)
        referenced = {
            key
            for framework in UNIVERSAL_PROMPT_FRAMEWORKS
            for key in framework.get("style_keys", [])
        }
        self.assertEqual(referenced - canonical, set())

    def test_storyboard_prompt_honours_english_voice_selection_and_full_style(self):
        prompt = build_prompt(
            mode="storyboard",
            product="Bonia handbag",
            scene="A bright studio with a warm neutral background.",
            motion="static",
            style="handbag_showcase",
            duration=10,
            product_type="bag",
            prompt_language="English",
        )
        self.assertIn("Handbag Hero Reveal", prompt)
        self.assertIn("Premium handbag commercial with a clean hero reveal", prompt)
        self.assertIn("HOOK / BAG SHAPE", prompt)
        self.assertIn("HARDWARE / SEAM DETAIL", prompt)
        self.assertIn("speak only in English", prompt)
        self.assertNotIn("speak only in Bahasa Melayu Malaysia", prompt)


if __name__ == "__main__":
    unittest.main()
