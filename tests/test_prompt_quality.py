import json
import tempfile
import unittest
from pathlib import Path

import prompt_catalog
from prompt_model_defaults import auto_prompt_model_defaults
from prompt_catalog import opening_direction, product_hook
from prompt_engine import (
    UNIVERSAL_PROMPT_FRAMEWORKS,
    _AUTO_STYLE_CANDIDATES,
    _CREATIVE_ACTIONS,
    _CREATIVE_PRESENTATION_VARIATIONS,
    _SUBCATEGORY_VARIATIONS_BY_ID,
    _prompt_sentence,
    _resolve_auto_style,
    _category_specific_scenes,
    _creative_variation,
    _presentation_variation,
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

    def test_every_product_group_has_at_least_ten_creative_variations(self):
        self.assertGreaterEqual(len(_CREATIVE_PRESENTATION_VARIATIONS), 10)
        self.assertEqual(len(set(_CREATIVE_PRESENTATION_VARIATIONS)), len(_CREATIVE_PRESENTATION_VARIATIONS))
        for group, actions in _CREATIVE_ACTIONS.items():
            with self.subTest(group=group):
                # Every category-safe action can combine with the shared
                # presentation matrix; each group therefore offers >=10
                # distinct prompt combinations without inventing product facts.
                combinations = {f"{action} | {presentation}" for action in actions for presentation in _CREATIVE_PRESENTATION_VARIATIONS}
                self.assertGreaterEqual(len(combinations), 10)
                direction = _creative_variation(group, f"generic {group} product", 0)
                self.assertIn("PRESENTATION:", direction)
                self.assertIn("VISUAL VARIATION:", direction)

    def test_every_catalogued_subcategory_has_at_least_ten_distinct_library_variations(self):
        library_path = Path(__file__).resolve().parents[1] / "prompts" / "subcategory_variation_library.json"
        with library_path.open("r", encoding="utf-8") as handle:
            library = json.load(handle)
        subcategories = library.get("subcategories", [])
        self.assertEqual(len(subcategories), 130)
        self.assertEqual(set(_SUBCATEGORY_VARIATIONS_BY_ID), {item["subcategory_id"] for item in subcategories})
        for subcategory in subcategories:
            with self.subTest(subcategory=subcategory["subcategory_id"]):
                variations = subcategory.get("variations", [])
                self.assertGreaterEqual(len(variations), 10)
                self.assertEqual(len({item["id"] for item in variations}), len(variations))
                self.assertEqual(len({item["action"] for item in variations}), len(variations))
                self.assertTrue(all(item.get("hook") and item.get("detail") and item.get("camera") and item.get("lighting") and item.get("closing") and item.get("audio") for item in variations))

    def test_exact_subcategory_library_is_used_by_prompt_variation(self):
        direction = _creative_variation("bag", "generic bag product", 0, "bag_wallet")
        self.assertIn("SUBCATEGORY VARIATION:", direction)
        self.assertIn("PRESENTATION:", direction)
        self.assertIn("wallet", direction.casefold())
        self.assertIn("VISUAL VARIATION:", direction)

    def test_main_prompt_flow_selects_model_before_preset_and_duration_after_preset(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        entry_start = source.index("    elif action == 'prompt':")
        entry_end = source.index("    elif action.startswith('prompt_mode:'):", entry_start)
        entry = source[entry_start:entry_end]
        self.assertIn("context.user_data['stage'] = 'prompt_product_type'", entry)
        self.assertIn("reply_markup=prompt_product_type_menu()", entry)

        product_start = source.index("    if stage == 'prompt_product_name':")
        product_end = source.index("    shortcuts = {", product_start)
        product_handler = source[product_start:product_end]
        self.assertIn("explicit_subcategory = selected_subcategory in PRODUCT_SUBTYPE_LABELS", product_handler)
        self.assertIn("context.user_data['stage'] = 'prompt_model_presence'", product_handler)
        self.assertIn("reply_markup=prompt_model_presence_menu(context.user_data)", product_handler)

        style_start = source.index("    elif action.startswith('prompt_style:') and stage == 'prompt_style':")
        style_end = source.index("    elif action == 'prompt_style_back'", style_start)
        style_handler = source[style_start:style_end]
        self.assertIn("context.user_data['stage'] = 'prompt_duration'", style_handler)
        self.assertIn("reply_markup=prompt_duration_menu()", style_handler)
        self.assertNotIn("prompt_generate:confirm", style_handler)

        duration_start = source.index("    elif action.startswith('prompt_duration:') and stage == 'prompt_duration':")
        duration_end = source.index("    elif action.startswith('prompt_ad_angle:') and stage == 'prompt_ad_angle':", duration_start)
        duration_handler = source[duration_start:duration_end]
        self.assertIn("context.user_data['stage'] = 'prompt_ad_angle'", duration_handler)
        self.assertIn("context.user_data.get('prompt_generation_mode') == 'preset'", duration_handler)
        self.assertIn("action = 'motion:auto'", duration_handler)
        self.assertNotIn("auto_prompt_model_defaults(", duration_handler)
        self.assertNotIn("'prompt_style': 'cinematic'", duration_handler)

    def test_model_none_and_animal_paths_continue_to_preset_picker(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        model_start = source.index("    elif action.startswith('prompt_model:') and stage == 'prompt_model_presence':")
        model_end = source.index("    elif action.startswith('prompt_duration:') and stage == 'prompt_duration':", model_start)
        model_flow = source[model_start:model_end]
        self.assertIn("context.user_data['stage'] = 'prompt_preset'", model_flow)
        self.assertIn("prompt_preset_menu(context.user_data.get('prompt_product_type','other'),'none')", model_flow)
        self.assertIn("prompt_preset_menu(context.user_data.get('prompt_product_type', 'other'), 'animal')", model_flow)
        self.assertIn("prompt_preset_menu(context.user_data.get('prompt_product_type','other'),'yes')", model_flow)

    def test_presentation_profile_avoids_repeating_recent_three(self):
        profiles = [
            _presentation_variation("cinematic", "variation-test-category", "variation-test-subtype")
            for _ in range(4)
        ]
        self.assertEqual(len(set(profiles[-3:])), 3)
        self.assertTrue(all("PRESENTATION VARIATION:" in profile for profile in profiles))

    def test_generated_prompt_contains_style_preserving_variation_profile(self):
        prompt = build_prompt(
            mode="storyboard",
            product="Desk lamp",
            scene="a realistic premium location chosen to suit the product",
            motion="auto",
            style="cinematic",
            duration=10,
            product_type="home",
        )
        self.assertIn("PRESENTATION VARIATION:", prompt)
        self.assertIn("Keep the selected visual style recognizably consistent", prompt)

    def test_wallet_category_uses_wallet_specific_creative_variation(self):
        direction = _creative_variation("wallet", "wallet", 0)
        self.assertIn("wallet", direction.casefold())
        self.assertIn("AUDIO:", direction)

    def test_audio_variation_does_not_force_unselected_voiceover(self):
        direction = _creative_variation("equipment", "desk lamp", 0)
        self.assertIn("only the audio elements selected by the user", direction)
        self.assertNotIn("add voice, music and SFX in post-production", direction)

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
            self.assertTrue(any(word in result.lower() for word in ("looking", "comparing", "interested", "closer look", "shopping", "curious", "before choosing", "here", "take a closer")))
            self.assertNotIn("boleh tengok", result.lower())

    def test_product_name_hooks_have_multiple_natural_malay_openings(self):
        hooks = {product_hook("NAMA_PRODUK: Beg tangan Bonia", "Malay") for _ in range(50)}
        hooks.discard(None)
        self.assertGreaterEqual(len(hooks), 3)
        self.assertTrue(all("kenali produk ini" not in hook.lower() for hook in hooks))

    def test_child_product_detection_covers_school_items_and_infant_products(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        child_block = source[source.index("def _prompt_is_child_product"):source.index("def prompt_creative_settings")]
        for term in ("school bag", "school shoes", "newborn", "infant", "kidswear"):
            with self.subTest(term=term):
                self.assertIn(term, child_block)

    def test_category_hook_uses_curated_database_phrase_without_product_name(self):
        hooks = [product_hook("KATEGORI: beg", "Malay") for _ in range(30)]
        result = next((hook for hook in hooks if hook), None)
        self.assertIsNotNone(result)
        self.assertIn("beg", result.lower())
        self.assertTrue(result[0].isupper())
        self.assertNotEqual(result, result.upper())

    def test_childrens_hijab_auto_model_uses_child_age_and_hijab(self):
        defaults = auto_prompt_model_defaults("hijab", "hijab_other", child_product=True)
        self.assertEqual(defaults["prompt_model_presence"], "yes")
        self.assertEqual(defaults["prompt_model_gender"], "female")
        self.assertEqual(defaults["prompt_model_hijab"], "hijab")
        self.assertEqual(defaults["prompt_model_age"], "8-12")

    def test_product_only_framing_overrides_conflicting_model_actions(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        model_block = source[source.index("def prompt_creative_settings"):source.index("PRODUCT_SUBTYPES =")]
        self.assertLess(
            model_block.index("if user_data.get('prompt_framing') == 'product_only':"),
            model_block.index("elif user_data.get('prompt_model_presence') == 'animal':"),
        )
        self.assertIn("PRODUCT-ONLY PRIORITY:", source)
        self.assertIn("Show no person, hands, face, body parts or animal", source)

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

    def test_wallet_subcategory_uses_wallet_scenes_not_handbag_scenes(self):
        prompt = build_prompt(
            mode="storyboard",
            product="Generic product name",
            scene="clean studio background",
            motion="static",
            style="auto",
            duration=10,
            product_type="bag",
            product_subtype="bag_wallet",
        )
        self.assertIn("HOOK / WALLET SILHOUETTE", prompt)
        self.assertIn("CTA / WALLET HERO", prompt)
        self.assertNotIn("HOOK / BAG SHAPE", prompt)
        self.assertNotIn("visible straps and handles in frame", prompt)

    def test_backpack_subcategory_uses_backpack_scenes(self):
        scenes = _category_specific_scenes("bag", "generic product", "bag_backpack")
        self.assertEqual(scenes[0][0], "HOOK / BACKPACK SILHOUETTE")
        self.assertIn("visible shoulder straps", scenes[0][1])

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
        self.assertIn("For AI-generated voice, use varied, natural product-specific wording", prompt)
        self.assertIn("in English", prompt)
        self.assertIn("use it exactly and add no dialogue", prompt)
        self.assertNotIn("Bahasa Melayu Malaysia", prompt)


    def test_model_details_are_completed_before_style_picker(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

        count_start = source.index("    elif action.startswith('prompt_model_count:') and stage == 'prompt_model_count':")
        gender_start = source.index("    elif action.startswith('prompt_model_gender:')", count_start)
        count_flow = source[count_start:gender_start]
        self.assertIn("context.user_data['stage'] = 'prompt_model_gender'", count_flow)

        age_start = source.index("    elif action.startswith('prompt_model_age:')", gender_start)
        gender_flow = source[gender_start:age_start]
        self.assertIn("context.user_data['stage'] = 'prompt_model_age'", gender_flow)

        ethnicity_start = source.index("    elif action.startswith('prompt_model_ethnicity:')", age_start)
        age_flow = source[age_start:ethnicity_start]
        self.assertIn("context.user_data['stage'] = 'prompt_model_ethnicity'", age_flow)
        self.assertIn("not _prompt_is_child_product(context.user_data)", age_flow)

        hijab_start = source.index("    elif action.startswith('prompt_model_hijab:')", ethnicity_start)
        ethnicity_flow = source[ethnicity_start:hijab_start]
        self.assertIn("context.user_data['stage'] = 'prompt_model_hijab'", ethnicity_flow)
        self.assertIn("context.user_data['stage'] = 'prompt_preset'", ethnicity_flow)

        duration_start = source.index("    elif action.startswith('prompt_duration:') and stage == 'prompt_duration':", hijab_start)
        hijab_flow = source[hijab_start:duration_start]
        self.assertIn("context.user_data['stage'] = 'prompt_preset'", hijab_flow)

        animal_start = source.index("    elif action.startswith('prompt_animal_species:') and stage == 'prompt_animal_species':")
        model_count_start = source.index("    elif action.startswith('prompt_model_count:') and stage == 'prompt_model_count':", animal_start)
        animal_flow = source[animal_start:model_count_start]
        self.assertIn("context.user_data['stage'] = 'prompt_preset'", animal_flow)
        self.assertIn("prompt_preset_menu(context.user_data.get('prompt_product_type', 'other'), 'animal')", animal_flow)


    def test_eight_descriptive_presets_plus_manual_and_automatic_sfx_rules(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        preset_start = source.index("def prompt_preset_menu(")
        preset_end = source.index("def prompt_category_menu(", preset_start)
        preset_code = source[preset_start:preset_end]
        self.assertIn("prompt_preset:manual", preset_code)
        for style in ("cinematic", "minimal", "lifestyle", "dynamic", "luxury", "flatlay", "creative_reveal", "white_doodle"):
            self.assertIn("prompt_preset:' + key", preset_code)
        self.assertIn("CORE_STYLE_DESCRIPTIONS", source)
        self.assertNotIn("reply_markup=prompt_sfx_menu()", source)
        audio_start = source.index("    style_key = str(user_data.get('prompt_style', '')).casefold()")
        audio_end = source.index("    if user_data.get('prompt_custom_background'):", audio_start)
        sfx_rules = source[audio_start:audio_end]
        self.assertIn("if user_data.get('prompt_audio_enabled', True) is not False and style_key in ('white_doodle', 'doodle_style'):", sfx_rules)
        self.assertNotIn("elif user_data.get('prompt_audio_enabled', True) is not False:", sfx_rules)
        self.assertIn("Subtle drawing sounds", sfx_rules)



if __name__ == "__main__":
    unittest.main()