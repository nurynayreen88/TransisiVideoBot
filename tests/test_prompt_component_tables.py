import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "prompts" / "prompt_library.json"
TABLES_PATH = ROOT / "prompts" / "prompt_component_tables.json"


class PromptComponentTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        cls.database = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
        cls.tables = cls.database["tables"]

    def test_component_database_is_versioned_and_additive(self):
        self.assertEqual(self.database["schema_version"], "1.0.0")
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
        for prompt in self.library["prompts"]:
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
            len(prompt.get("storyboard", [])) for prompt in self.library["prompts"]
        )
        component_count = len(self.tables["storyboard_components"])
        self.assertLess(component_count, source_shot_count)
        self.assertEqual(len(self.tables["camera_profiles"]), 10)
        self.assertGreaterEqual(len(self.tables["subcategories"]), 100)

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
