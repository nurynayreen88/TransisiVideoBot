"""Regression tests for single-language prompt instructions."""
import unittest

from prompt_copy import spoken_copy_direction


class SpokenCopyDirectionTests(unittest.TestCase):
    def test_malay_voice_direction_is_written_in_english(self):
        direction = spoken_copy_direction("Malay")
        self.assertIn("natural Bahasa Melayu Malaysia", direction)
        self.assertIn("Avoid Indonesian vocabulary", direction)
        self.assertNotIn("Gunakan", direction)

    def test_english_voice_direction_is_written_in_english(self):
        direction = spoken_copy_direction("English")
        self.assertIn("natural English", direction)
        self.assertNotIn("Gunakan", direction)

    def test_unknown_language_safely_defaults_to_malay(self):
        self.assertIn("natural Bahasa Melayu Malaysia", spoken_copy_direction("unknown"))


if __name__ == "__main__":
    unittest.main()
