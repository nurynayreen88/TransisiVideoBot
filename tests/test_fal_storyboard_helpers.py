"""Offline unit tests for the Klippo storyboard/video beta helpers."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from fal_storyboard_test import detect_image_mime, parse_gemini_json
from modules.video_engine import calculate_panel_durations, create_video
from fal_storyboard_test_bot import claim_user, release_user


class GeminiHelperTests(unittest.TestCase):
    def test_detects_jpeg_png_and_webp(self):
        with tempfile.TemporaryDirectory() as tmp:
            for fmt, expected in (
                ("JPEG", "image/jpeg"),
                ("PNG", "image/png"),
                ("WEBP", "image/webp"),
            ):
                path = Path(tmp) / f"sample.{fmt.lower()}"
                Image.new("RGB", (8, 8), "white").save(path, format=fmt)
                self.assertEqual(detect_image_mime(path), expected)

    def test_rejects_non_image_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jpg"
            path.write_text("not an image", encoding="utf-8")
            with self.assertRaises(ValueError):
                detect_image_mime(path)

    def test_parses_json_inside_markdown_fence(self):
        self.assertEqual(
            parse_gemini_json(' ```json\n{"product_type":"bag"}\n``` '),
            {"product_type": "bag"},
        )

    def test_rejects_non_object_json(self):
        with self.assertRaises(ValueError):
            parse_gemini_json('["not", "an object"]')

    def test_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            parse_gemini_json("{not-json}")


class TelegramLockTests(unittest.TestCase):
    def test_same_user_cannot_claim_two_generation_slots(self):
        user_id = 123456
        self.assertTrue(claim_user(user_id))
        self.assertFalse(claim_user(user_id))
        release_user(user_id)
        self.assertTrue(claim_user(user_id))
        release_user(user_id)


class VideoHelperTests(unittest.TestCase):
    def test_audio_longer_than_original_video_extends_both_panels(self):
        first, second = calculate_panel_durations(4.2)
        self.assertAlmostEqual(first, second)
        self.assertGreaterEqual(first + second, 4.45)

    def test_short_audio_keeps_minimum_video_duration(self):
        first, second = calculate_panel_durations(1.0)
        self.assertAlmostEqual(first + second, 3.6)

    def test_non_positive_audio_duration_rejected(self):
        with self.assertRaises(ValueError):
            calculate_panel_durations(0)

    def test_video_requires_exactly_two_panels(self):
        with self.assertRaises(ValueError):
            create_video([], "Suara ujian", "unused.mp4")


if __name__ == "__main__":
    unittest.main()
