import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "prompts" / "prompt_library.json"
TABLES_PATH = ROOT / "prompts" / "prompt_component_tables.json"
OVERRIDES_PATH = ROOT / "prompts" / "prompt_quality_overrides.json"


class PromptComponentTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        cls.database = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
        cls.overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")).get("overrides", [])
        cls.effective_prompts = {
            item["id"]: dict(item) for item in cls.library["prompts"]
        }
        for override in cls.overrides:
            target = cls.effective_prompts.get(override.get("id"))
            if target is not None:
                for field in ("prompt", "storyboard"):
                    if field in override:
                        target[field] = override[field]
        cls.tables = cls.database["tables"]

    def test_component_database_is_versioned_and_additive(self):
        self.assertEqual(self.database["schema_version"], "1.0.1")
        self.assertEqual(
            self.database["source"]["master_prompt_count"],
            len(self.library["prompts"]),
        )
        self.assertEqual(
            self.database["source"]["master_library_version"],
            self.library["schema_version"],
        )

    def test_every_legacy_prompt_has_one_component_mapping(self):
        source_ids = [item["id"] for item in self.library["prompts"]]
        mapping_ids = [item["id"] for item in self.tables["prompt_component_map"]]
        self.assertEqual(len(mapping_ids), len(source_ids))
        self.assertEqual(len(mapping_ids), len(set(mapping_ids)))
        self.assertEqual(set(mapping_ids), set(source_ids))

    def test_all_foreign_keys_resolve(self):
        tables = self.tables
        library_category_ids = {item["id"] for item in tables["library_categories"]}
        product_category_ids = {item["id"] for item in tables["product_categories"]}
        subcategory_ids = {item["id"] for item in tables["subcategories"]}
        style_ids = {item["id"] for item in tables["styles"]}
        component_ids = {item["id"] for item in tables["storyboard_components"]}
        camera_ids = {item["id"] for item in tables["camera_profiles"]}
        audio_ids = {item["id"] for item in tables["audio_profiles"]}
        hook_ids = {item["id"] for item in tables["hook_rules"]}
        cta_ids = {item["id"] for item in tables["cta_rules"]}
        fidelity_ids = {item["id"] for item in tables["product_fidelity_rules"]}

        for subcategory in tables["subcategories"]:
            self.assertIn(subcategory["category_id"], product_category_ids)
        for mapping in tables["category_crosswalk"]:
            self.assertIn(mapping["library_category_id"], library_category_ids)
            if mapping["product_category_id"] is not None:
                self.assertIn(mapping["product_category_id"], product_category_ids)
        for mapping in tables["prompt_component_map"]:
            self.assertIn(mapping["library_category_id"], library_category_ids)
            if mapping["product_category_id"] is not None:
                self.assertIn(mapping["product_category_id"], product_category_ids)
            self.assertIn(mapping["style_id"], style_ids)
            for field in (
                "hook_component_id",
                "action_component_id",
                "detail_component_id",
                "closing_component_id",
            ):
                self.assertIn(mapping[field], component_ids)
            for field, valid_ids in (
                ("camera_profile_ids", camera_ids),
                ("audio_profile_ids", audio_ids),
                ("hook_rule_ids", hook_ids),
                ("cta_rule_ids", cta_ids),
                ("product_fidelity_rule_ids", fidelity_ids),
            ):
                self.assertTrue(mapping[field])
                self.assertTrue(set(mapping[field]).issubset(valid_ids))

    def test_master_storyboards_are_preserved_as_four_beats(self):
        components = {
            item["id"]: item for item in self.tables["storyboard_components"]
        }
        mapping_by_id = {
            item["id"]: item for item in self.tables["prompt_component_map"]
        }
        for prompt in self.effective_prompts.values():
            self.assertEqual(len(prompt["storyboard"]), 4, prompt["id"])
            mapping = mapping_by_id[prompt["id"]]
            for field, source_index in (
                ("hook_component_id", 0),
                ("action_component_id", 1),
                ("detail_component_id", 2),
                ("closing_component_id", 3),
            ):
                self.assertEqual(
                    components[mapping[field]]["direction"],
                    prompt["storyboard"][source_index]["direction"],
                    f"{prompt['id']} {field}",
                )

    def test_component_table_reuses_shared_storyboard_directions(self):
        source_shot_count = sum(
            len(prompt.get("storyboard", [])) for prompt in self.effective_prompts.values()
        )
        component_count = len(self.tables["storyboard_components"])
        self.assertLess(component_count, source_shot_count)
        self.assertEqual(len(self.tables["camera_profiles"]), 10)
        self.assertGreaterEqual(len(self.tables["subcategories"]), 100)

    def test_runtime_resolves_storyboards_from_normalized_tables_with_fallback(self):
        bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("PROMPT_COMPONENT_TABLES_PATH", bot_source)
        self.assertIn("def _prompt_library_storyboard(template):", bot_source)
        self.assertIn("return original", bot_source)
        self.assertIn(
            "context.user_data['prompt_library_storyboard'] = _prompt_library_storyboard(template)",
            bot_source,
        )

    def test_runtime_strips_duplicate_timing_labels_from_shot_directions(self):
        bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
        # The prompt engine already writes timed beats; avoid repeating labels
        # embedded in a small number of legacy storyboard directions.
        self.assertIn("direction = re.sub(r'^\\s*\\d+(?:[–-]\\d+)?s\\s*\\|\\s*[^:]{1,80}:\\s*', '', direction)", bot_source)

    def test_legacy_timing_prefixes_are_removed_from_component_directions(self):
        pattern = re.compile(r'^\\s*\\d+(?:[–-]\\d+)?s\\s*\\|\\s*[^:]{1,80}:\\s*')
        directions = [item.get("direction", "") for item in self.tables["storyboard_components"]]
        affected = [value for value in directions if pattern.match(value)]
        self.assertTrue(affected, "Audit fixture should include legacy repeated timing labels")
        self.assertTrue(all(not pattern.match(pattern.sub("", value)) for value in affected))

    def test_runtime_assembles_choice_aware_component_rules(self):
        bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("def _prompt_library_component_rules(", bot_source)
        self.assertIn("audio_enabled=context.user_data.get('prompt_audio_enabled', True) is not False", bot_source)
        self.assertIn("voiceover_mode=context.user_data.get('prompt_voiceover_mode', 'none')", bot_source)
        self.assertIn("on_screen_text=context.user_data.get('prompt_on_screen_text', 'no')", bot_source)
        self.assertIn("camera_choice=motion", bot_source)
        self.assertIn("selected_camera_by_choice", bot_source)
        self.assertIn("if voiceover_mode == 'script':", bot_source)
        self.assertIn("do not add spoken lines or an extra spoken CTA", bot_source)
        self.assertIn("audio_fields = ('music', 'sfx') if voiceover_mode == 'script' else ('voice', 'music', 'sfx')", bot_source)
        self.assertIn("if on_screen_text == 'yes':", bot_source)
        self.assertIn("REUSABLE COMPONENT RULES:", bot_source)

    def test_optional_audio_and_cta_rules_respect_user_choices(self):
        audio = {item["id"]: item for item in self.tables["audio_profiles"]}
        cta = {item["id"]: item for item in self.tables["cta_rules"]}
        self.assertIn("Bahasa Melayu Malaysia", audio["audio_voice_malay"]["voice"])
        self.assertIn("English", audio["audio_voice_english"]["voice"])
        self.assertIn("No voiceover", audio["audio_music_sfx_only"]["voice"])
        self.assertIn("do not add an extra CTA", cta["cta_no_added_dialogue"]["direction"])
        self.assertIn("do not invent price", cta["cta_soft_invitation"]["direction"])


if __name__ == "__main__":
    unittest.main()
