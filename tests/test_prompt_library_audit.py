"""Unit tests for the non-destructive prompt library audit."""
import unittest
from scripts.audit_prompt_quality import audit


def sample(subcategory_id="sample", detail="Show a visible seam."):
    return {"minimum_variations_per_subcategory": 2, "subcategories": [{
        "subcategory_id": subcategory_id, "variation_count": 2, "variations": [
            {"id":"v1","hook":"Open clearly.","action":"Show the product with one slow movement.","detail":detail,"camera":"Push in slowly.","lighting":"Keep soft light.","closing":"End on a stable view.","audio":"Soft room tone."},
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

    def test_wallet_category_flags_bag_handle_or_strap_wording(self):
        data = sample("bag_wallet")
        data["subcategories"][0]["variations"][0]["action"] = "Lift the bag by its handle, then turn it."
        result = audit(data)
        self.assertTrue(any("possible bag/handle/strap wording" in f for f in result["flags"]))
        self.assertEqual(result["errors"], [])

    def test_educational_toy_grammar_is_flagged_for_review(self):
        data = sample("toy_educational", detail="Show a genuinely visible educational toy pieces.")
        result = audit(data)
        self.assertTrue(any("toy-detail grammar issue" in f for f in result["flags"]))
        self.assertEqual(result["errors"], [])


    def test_camera_field_with_lighting_instruction_is_flagged(self):
        data = sample()
        data["subcategories"][0]["variations"][0]["camera"] = "Use a broad side light source."
        result = audit(data)
        self.assertTrue(any("field-role mismatch in camera" in f for f in result["flags"]))
        self.assertEqual(result["errors"], [])

    def test_detail_field_with_camera_move_is_flagged(self):
        data = sample()
        data["subcategories"][0]["variations"][0]["detail"] = "Make a slow push-in."
        result = audit(data)
        self.assertTrue(any("field-role mismatch in detail" in f for f in result["flags"]))

    def test_closing_field_with_audio_instruction_is_flagged(self):
        data = sample()
        data["subcategories"][0]["variations"][0]["closing"] = "Use restrained instrumental music."
        result = audit(data)
        self.assertTrue(any("field-role mismatch in closing" in f for f in result["flags"]))


if __name__ == "__main__":
    unittest.main()
