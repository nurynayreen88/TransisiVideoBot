import json
import tempfile
import unittest
from pathlib import Path

import prompt_catalog
from prompt_catalog import opening_direction, product_hook
from prompt_engine import (
    UNIVERSAL_PROMPT_FRAMEWORKS,
    _AUTO_STYLE_CANDIDATES,
    _prompt_sentence,
    _resolve_auto_style,
    _category_specific_scenes,
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

    def test_prompt_preserves_complete_style_scene_camera_and_concept(self):
        prompt = build_prompt(
            mode="storyboard",
            product="Desk lamp",
            scene="Clean studio background. Keep a warm side light and neutral tabletop.",
            motion="orbit",
            style="studio_360_safe",
            duration=10,
            concept="Show a careful hero reveal. Keep the final frame suitable for a seamless edit.",
            product_type="equipment",
        )
        self.assertIn("not a fabricated 360-degree rotation or unseen product surfaces.", prompt)
        self.assertIn("Keep a warm side light and neutral tabletop.", prompt)
        self.assertIn("Never reveal or fabricate an unseen side.", prompt)
        self.assertIn("Keep the final frame suitable for a seamless edit.", prompt)
        self.assertIn("CAMERA PRIORITY:", prompt)

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

    def test_category_hook_uses_curated_database_phrase_without_product_name(self):
        hooks = [product_hook("KATEGORI: beg", "Malay") for _ in range(30)]
        result = next((hook for hook in hooks if hook), None)
        self.assertIsNotNone(result)
        self.assertIn("beg", result.lower())
        self.assertTrue(result[0].isupper())
        self.assertNotEqual(result, result.upper())

    def test_baby_products_prioritize_safe_age_appropriate_model_rules(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        baby_branch = source.index("if baby_product and child_model:")
        generic_child_branch = source.index("elif child_model and not child_product:", baby_branch)
        self.assertLess(baby_branch, generic_child_branch)
        self.assertIn("adult caregiver hands if needed or show the baby product alone", source[baby_branch:generic_child_branch])
        self.assertIn("adult caregiver model(s)", source[baby_branch:])

    def test_explicit_bag_subcategory_overrides_ambiguous_product_name(self):
        handbag_styles = {
            "handbag_showcase", "bag_daily_carry", "bag_tabletop_reveal",
            "sling_bag_lifestyle", "bag_flatlay",
        }
        wallet_styles = {
            "wallet_luxury_macro", "wallet_open_close", "wallet_daily_carry",
            "wallet_flatlay", "wallet_gift_reveal",
        }
        for _ in range(20):
            self.assertIn(
                _resolve_auto_style("auto", "bag", "Handbag with wallet accessory", "bag_handbag"),
                handbag_styles,
            )
            self.assertIn(
                _resolve_auto_style("auto", "bag", "Wallet product", "bag_wallet"),
                wallet_styles,
            )

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

    def test_every_top_level_product_category_has_specific_scene_beats(self):
        categories = (
            "fashion", "bag", "hijab", "shoes", "beauty", "food", "gadget",
            "equipment", "home", "accessory", "toy", "book_stationery",
            "sports", "pet", "automotive", "baby", "travel", "office",
        )
        for category in categories:
            with self.subTest(category=category):
                scenes = _category_specific_scenes(category, "generic product")
                self.assertEqual(len(scenes), 5)
                self.assertNotEqual(scenes[0][0], "HOOK / PRODUCT RECOGNITION")

    def test_all_auto_style_candidates_exist_in_the_canonical_catalog(self):
        canonical = set(prompt_catalog.STYLES)
        missing = {
            f"{category}:{style}"
            for category, styles in _AUTO_STYLE_CANDIDATES.items()
            for style in styles
            if style not in canonical
        }
        self.assertEqual(missing, set())

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
        self.assertIn("For AI-generated voice, use English", prompt)
        self.assertIn("use it exactly and add no dialogue", prompt)
        self.assertNotIn("Bahasa Melayu Malaysia", prompt)


if __name__ == "__main__":
    unittest.main()
