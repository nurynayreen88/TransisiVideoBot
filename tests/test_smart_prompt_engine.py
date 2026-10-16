"""Regression tests for KLIPPO's additive Smart Prompt Engine."""
import unittest

from smart_prompt_engine import choose_variation, format_variation


class SmartPromptEngineTests(unittest.TestCase):
    def test_auto_scene_has_a_concrete_setting(self):
        variation = choose_variation(
            "KATEGORI: pakaian", "clean premium studio background, selected to complement the exact product reference",
            "A slow forward dolly-in", seed=1,
        )
        self.assertIn(variation["setting"], format_variation(variation))
        self.assertTrue(variation["setting"])

    def test_explicit_user_scene_stays_in_its_scene_family(self):
        variation = choose_variation(
            "KATEGORI: beg", "premium photography studio, soft neutral backdrop",
            "A slow forward dolly-in", seed=2,
        )
        self.assertTrue(any(word in variation["setting"].lower() for word in ("studio", "backdrop", "set")))

    def test_user_concept_is_respected(self):
        variation = choose_variation(
            "KATEGORI: pakaian", "tasteful modern home interior",
            "A locked camera", user_concept="komedi santai", seed=3,
        )
        self.assertEqual(variation["mood"], "komedi santai")

    def test_motion_choice_controls_camera_direction(self):
        variation = choose_variation(
            "KATEGORI: botol", "premium photography studio",
            "A locked camera with subtle lighting changes", seed=4,
        )
        self.assertIn("locked reference-facing frame", variation["camera"])

    def test_part_two_action_supports_continuity(self):
        variation = choose_variation(
            "KATEGORI: kasut", "premium photography studio",
            "A slow forward dolly-in", part=2, seed=5,
        )
        self.assertIn("exact final frame of Part 1", variation["action"])

    def test_prompt_has_no_unrequested_text_instruction(self):
        variation = choose_variation(
            "KATEGORI: botol", "premium photography studio",
            "A slow forward dolly-in", seed=6,
        )
        self.assertIn("No on-screen text unless the user explicitly supplied exact wording",
                      format_variation(variation))


if __name__ == "__main__":
    unittest.main()
