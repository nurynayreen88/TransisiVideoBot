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


if __name__ == "__main__":
    unittest.main()
