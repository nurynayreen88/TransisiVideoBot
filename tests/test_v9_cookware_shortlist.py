"""Read-only validation of staged cookware V9 shortlist. No runtime activation."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "prompts" / "full_prompt_library"
SHORTLIST = LIB / "v9_cookware_shortlist_50_20261025.json"
ALIAS = LIB / "v9_cookware_alias_review_20261025.json"


def validate():
    manifest = json.loads(SHORTLIST.read_text(encoding="utf-8"))
    alias = json.loads(ALIAS.read_text(encoding="utf-8"))
    assert alias["master_id"] == "home_kitchen"
    assert alias["v9_id"] == manifest["subcategory_id"] == "home_kitchen_cookware"
    assert alias["status"] == "REVIEW_ONLY"
    selected = manifest["selected"]
    assert len(selected) == manifest["selection_count"] == 50
    assert manifest["status"] == "SHORTLIST_PENDING_PRODUCT_FIT_AND_RENDER_QA"
    assert len({x["concept"] for x in selected}) == 50
    ids = [rid for x in selected for rid in x["record_ids"]]
    assert len(ids) == len(set(ids)) == manifest["duration_record_count"] == 100
    cached = {}
    for entry in selected:
        name = entry["source_file"]
        if name not in cached:
            source = json.loads((LIB / name).read_text(encoding="utf-8"))
            cached[name] = {v["id"]: v for v in source["variations"]}
        pair = [cached[name][rid] for rid in entry["record_ids"]]
        assert [v["duration_seconds"] for v in pair] == [10, 20]
        assert all(v["subcategory_id"] == manifest["subcategory_id"] for v in pair)
        assert all(v["concept"] == entry["concept"] for v in pair)
        assert all(v["status"] == "DRAFT_RENDER_QA" for v in pair)
        assert all(len(v["full_prompt"].strip()) > 250 for v in pair)
        assert "PART 2" in pair[1]["full_prompt"].upper()
    return {"concepts": len(selected), "duration_records": len(ids), "activation": False}


class CookwareShortlistValidation(unittest.TestCase):
    def test_staged_shortlist(self):
        self.assertEqual(validate()["duration_records"], 100)

    def test_all_shortlisted_prompts_are_original_drafts(self):
        manifest = json.loads(SHORTLIST.read_text(encoding="utf-8"))
        for entry in manifest["selected"]:
            source = json.loads((LIB / entry["source_file"]).read_text(encoding="utf-8"))
            index = {record["id"]: record for record in source["variations"]}
            for record_id in entry["record_ids"]:
                record = index[record_id]
                self.assertEqual(record["status"], "DRAFT_RENDER_QA")
                self.assertNotIn("{{", record["full_prompt"])
                self.assertTrue(record["full_prompt"].strip())

    def test_legacy_catalog_alias_is_review_only(self):
        alias = json.loads(ALIAS.read_text(encoding="utf-8"))
        self.assertEqual(alias["master_id"], "home_kitchen")
        self.assertEqual(alias["v9_id"], "home_kitchen_cookware")
        self.assertEqual(alias["status"], "REVIEW_ONLY")

    def test_no_duplicate_durations_per_concept(self):
        manifest = json.loads(SHORTLIST.read_text(encoding="utf-8"))
        for entry in manifest["selected"]:
            source = json.loads((LIB / entry["source_file"]).read_text(encoding="utf-8"))
            index = {record["id"]: record for record in source["variations"]}
            durations = [index[record_id]["duration_seconds"] for record_id in entry["record_ids"]]
            self.assertEqual(durations, [10, 20])

    def test_staged_prompts_are_not_runtime_catalog(self):
        bot = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("PROMPT_LIBRARY_PATH", bot)
        self.assertIn("prompt_library.json", bot)
        self.assertNotIn("v9_cookware_shortlist_50_20261025.json", bot)

    def test_prompt_reference_handoff_is_external(self):
        bot = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("Gambar produk tidak perlu dimuat naik ke bot", bot)
        self.assertIn("Muat naik gambar produk asal yang sama ke platform AI pilihan", bot)

    def test_shortlist_sources_are_confined_to_library(self):
        manifest = json.loads(SHORTLIST.read_text(encoding="utf-8"))
        for entry in manifest["selected"]:
            source_file = entry["source_file"]
            self.assertEqual(Path(source_file).name, source_file)
            self.assertTrue(source_file.endswith(".json"))
            self.assertTrue((LIB / source_file).is_file())

    def test_original_product_handoff_is_not_a_bot_upload(self):
        bot = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("Gambar produk tidak perlu dimuat naik ke bot", bot)
        self.assertIn("Muat naik gambar produk asal yang sama ke platform AI pilihan", bot)

    def test_review_preview_returns_exact_draft(self):
        from v9_cookware_preview import preview_cookware_prompt
        manifest = json.loads(SHORTLIST.read_text(encoding="utf-8"))
        for entry in manifest["selected"]:
            source = json.loads((LIB / entry["source_file"]).read_text(encoding="utf-8"))
            index = {item["id"]: item for item in source["variations"]}
            for duration, record_id in zip((10, 20), entry["record_ids"]):
                preview = preview_cookware_prompt(entry["concept"], duration)
                self.assertEqual(preview["id"], record_id)
                self.assertEqual(preview["full_prompt"], index[record_id]["full_prompt"])
                self.assertFalse(preview["runtime_activated"])

    def test_review_preview_rejects_invalid_requests(self):
        from v9_cookware_preview import preview_cookware_prompt
        with self.assertRaises(ValueError):
            preview_cookware_prompt("Nonexistent cookware concept", 10)
        with self.assertRaises(ValueError):
            preview_cookware_prompt("Rendang ayam", 30)


if __name__ == "__main__":
    unittest.main()
