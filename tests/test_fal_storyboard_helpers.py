"""Offline unit tests for the Klippo storyboard/video beta helpers."""
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from PIL import Image

from fal_storyboard_test import detect_image_mime, normalize_malaysian_voiceover, parse_gemini_json
from modules.video_engine import _probe_duration, calculate_panel_durations, create_video
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

    def test_normalizes_common_indonesian_words_for_malaysian_voiceover(self):
        result = normalize_malaysian_voiceover("Produk ini bagus banget, kalian bisa coba.")
        self.assertEqual(result, "Produk ini sangat bagus, anda boleh cuba.")

    def test_voiceover_is_limited_to_one_short_sentence(self):
        result = normalize_malaysian_voiceover(
            "Ini produk yang sangat menarik untuk anda gunakan setiap hari kerana reka bentuknya kemas dan praktikal. Ayat kedua."
        )
        self.assertNotIn("Ayat kedua", result)
        self.assertLessEqual(len(result.split()), 18)


class TelegramLockTests(unittest.TestCase):
    def test_same_user_cannot_claim_two_generation_slots(self):
        user_id = 123456
        self.assertTrue(claim_user(user_id))
        self.assertFalse(claim_user(user_id))
        release_user(user_id)
        release_user(user_id)  # cleanup is idempotent even after an earlier release
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

    def test_duration_falls_back_to_text_estimate_without_ffprobe_or_mutagen(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "voiceover.mp3"
            audio.write_bytes(b"fake")
            with mock.patch("modules.video_engine.shutil.which", return_value=None), \
                 mock.patch("modules.video_engine._mutagen_duration", return_value=None):
                self.assertAlmostEqual(_probe_duration(audio, "satu dua tiga empat lima"), 5 / 2.6)

    def test_failed_final_mux_does_not_leave_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            panel_a, panel_b = root / "a.jpg", root / "b.jpg"
            Image.new("RGB", (16, 16), "white").save(panel_a)
            Image.new("RGB", (16, 16), "black").save(panel_b)
            output = root / "output.mp4"

            def fake_run(command):
                if "-movflags" in command:
                    raise RuntimeError("simulated final mux failure")
                Path(command[-1]).write_bytes(b"intermediate")

            with mock.patch("modules.video_engine.shutil.which", return_value="/usr/bin/ffmpeg"), \
                 mock.patch("modules.video_engine.gTTS") as tts, \
                 mock.patch("modules.video_engine._probe_duration", return_value=1.0), \
                 mock.patch("modules.video_engine._run", side_effect=fake_run):
                tts.return_value.save.side_effect = lambda path: Path(path).write_bytes(b"audio")
                with self.assertRaisesRegex(RuntimeError, "simulated final mux failure"):
                    create_video([panel_a, panel_b], "Suara ujian", output)
            self.assertFalse(output.exists())

    def test_video_requires_exactly_two_panels(self):
        with self.assertRaises(ValueError):
            create_video([], "Suara ujian", "unused.mp4")


if __name__ == "__main__":
    unittest.main()
