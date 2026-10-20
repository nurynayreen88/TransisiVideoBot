"""Regression tests for category-fit automatic model selection."""
import unittest

from prompt_model_defaults import auto_prompt_model_defaults


class AutoPromptModelDefaultsTests(unittest.TestCase):
    def test_pet_products_default_to_species_appropriate_animal_model(self):
        result = auto_prompt_model_defaults("pet", "pet_food", animal_related=True)
        self.assertEqual(result["prompt_model_presence"], "animal")
        self.assertEqual(result["prompt_animal_species"], "auto")
        self.assertEqual(result["prompt_model_count"], 1)

    def test_childrens_clothing_uses_child_age_and_reference_matched_gender(self):
        result = auto_prompt_model_defaults("fashion", "fashion_kids", child_product=True)
        self.assertEqual(result["prompt_model_presence"], "yes")
        self.assertEqual(result["prompt_model_age"], "8-12")
        self.assertEqual(result["prompt_model_gender"], "auto")

    def test_mens_fashion_defaults_to_male_model(self):
        result = auto_prompt_model_defaults("fashion", "fashion_men")
        self.assertEqual(result["prompt_model_gender"], "male")
        self.assertEqual(result["prompt_model_age"], "26-40")

    def test_hijab_defaults_to_female_model_with_hijab(self):
        result = auto_prompt_model_defaults("hijab", "hijab_bawal")
        self.assertEqual(result["prompt_model_gender"], "female")
        self.assertEqual(result["prompt_model_hijab"], "hijab")

    def test_general_product_defaults_to_no_model(self):
        result = auto_prompt_model_defaults("gadget", "gadget_audio")
        self.assertEqual(result["prompt_model_presence"], "none")
        self.assertEqual(result["prompt_model_count"], 0)


if __name__ == "__main__":
    unittest.main()
