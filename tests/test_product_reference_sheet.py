import tempfile
import unittest
from pathlib import Path

from PIL import Image

from product_reference_sheet import (
    CHATGPT_ANALYSIS_PROMPT,
    MAX_REFERENCE_IMAGES,
    build_reference_sheet,
)


class ProductReferenceSheetTests(unittest.TestCase):
    def test_builds_large_uncropped_sheet_for_multiple_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for index, size in enumerate(((640, 900), (900, 640), (800, 800))):
                path = root / f"source_{index}.png"
                Image.new("RGB", size, (40 + index * 40, 100, 180)).save(path)
                paths.append(path)

            output = build_reference_sheet(paths, root / "sheet.jpg")
            with Image.open(output) as result:
                self.assertEqual(result.format, "JPEG")
                self.assertEqual(result.size, (2604, 1932))
                self.assertEqual(result.mode, "RGB")

    def test_rejects_empty_or_too_many_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                build_reference_sheet([], root / "empty.jpg")
            paths = []
            for index in range(MAX_REFERENCE_IMAGES + 1):
                path = root / f"{index}.png"
                Image.new("RGB", (20, 20), "white").save(path)
                paths.append(path)
            with self.assertRaises(ValueError):
                build_reference_sheet(paths, root / "too_many.jpg")

    def test_chatgpt_prompt_requires_product_data_block_and_no_added_text(self):
        self.assertIn("MAKLUMAT PRODUK UNTUK KLIPPO", CHATGPT_ANALYSIS_PROMPT)
        self.assertIn("GAYA VIDEO: REALISTIK + DOODLE", CHATGPT_ANALYSIS_PROMPT)
        self.assertIn("Jangan tambah teks", CHATGPT_ANALYSIS_PROMPT)
        self.assertIn("9:16", CHATGPT_ANALYSIS_PROMPT)


if __name__ == "__main__":
    unittest.main()
