"""Validate V9 product-type taxonomy without activating draft prompts."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "prompts" / "full_prompt_library"
PARTS = (
    "accessory_toy", "auto_baby_travel", "beauty_food", "fashion_bags",
    "gadget_home", "hijab_shoes", "office_other", "stationery_sports_pet",
)


class ProductTypeTaxonomyTests(unittest.TestCase):
    def test_all_130_subcategories_and_types(self):
        merged = {}
        for part in PARTS:
            path = LIB / ("v9_product_types_" + part + "_20261025.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(data["activation"])
            self.assertEqual(data["status"], "DRAFT_TYPE_TAXONOMY_REVIEW")
            for subcategory, types in data["groups"].items():
                self.assertNotIn(subcategory, merged)
                self.assertGreater(len(types), 0)
                self.assertEqual(len(types), len(set(types)))
                merged[subcategory] = types
        self.assertEqual(len(merged), 130)
        self.assertEqual(sum(map(len, merged.values())), 712)

    def test_cookware_has_distinct_product_types(self):
        data = json.loads((LIB / "v9_product_types_gadget_home_20261025.json").read_text(encoding="utf-8"))
        types = data["groups"]["home_kitchen"]
        for required in ("wok", "frying pan", "pressure cooker", "steamer", "rice cooker"):
            self.assertIn(required, types)


if __name__ == "__main__":
    unittest.main()
