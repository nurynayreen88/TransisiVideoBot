"""Unit tests for the non-destructive prompt library audit."""
import unittest
from scripts.audit_prompt_quality import audit


def sample():
    return {"minimum_variations_per_subcategory": 2, "subcategories": [{
        "subcategory_id": "sample", "variation_count": 2, "variations": [
            {"id":"v1","hook":"Open clearly.","action":"Show the product with one slow movement.","detail":"Show a visible seam.","camera":"Push in slowly.","lighting":"Keep soft light.","closing":"End on a stable view.","audio":"Soft room tone."},
            {"id":"v2","hook":"Open clearly.","action":"Rotate the product once on a stable surface.","detail":"Show a visible seam.","camera":"Slide left slowly.","lighting":"Keep soft light.","closing":"End on a stable view.","audio":"Soft room tone."}
        ]}]}


class PromptLibraryAuditTests(unittest.TestCase):
    def test_valid_library_has_no_hard_errors(self):
        result = audit(sample())
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["stats"]["variations"], 2)

    def test_duplicate_ids_are_hard_errors(self):
        data = sample()
        data["subcategories"][0]["variations"][1]["id"] = "v1"
        self.assertTrue(any("duplicate variation id" in e for e in audit(data)["errors"]))

    def test_repetition_is_flagged_not_rejected(self):
        result = audit(sample())
        self.assertTrue(any("hook repeats" in f for f in result["flags"]))
        self.assertEqual(result["errors"], [])

    def test_empty_required_field_is_a_hard_error(self):
        data = sample()
        data["subcategories"][0]["variations"][0]["action"] = ""
        self.assertTrue(any("missing or empty action" in e for e in audit(data)["errors"]))


if __name__ == "__main__":
    unittest.main()
