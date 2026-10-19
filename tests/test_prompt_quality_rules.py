"""Regression tests for prompt language, no-text output, and Telegram compaction."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = ROOT / "bot.py"


def load_function_from_source(name):
    tree = ast.parse(BOT_SOURCE.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {}
    exec(compile(module, str(BOT_SOURCE), "exec"), namespace)
    return namespace[name]


class PromptQualityRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fit_prompt = load_function_from_source("fit_prompt_to_one_telegram_message")
        cls.creative_settings = load_function_from_source("prompt_creative_settings")

    def test_long_prompt_preserves_voiceover_settings_and_fits_telegram(self):
        long_prompt = (
            "VISUAL STORY AND PRODUCT DETAIL\n" + ("A detailed shot direction. " * 240)
            + "\n\nKLIPPO GUIDED CREATIVE SETTINGS:\n"
            + "VOICEOVER IS ENABLED: natural Bahasa Melayu Malaysia, spoken hook, one verified benefit, spoken CTA. "
            + "NO GENERATED ON-SCREEN TEXT. Keep music below the voice."
        )
        result = self.fit_prompt(long_prompt)
        self.assertLessEqual(len(result), 3800)
        self.assertIn("KLIPPO GUIDED CREATIVE SETTINGS:", result)
        self.assertIn("VOICEOVER IS ENABLED", result)
        self.assertIn("Bahasa Melayu Malaysia", result)
        self.assertIn("NO GENERATED ON-SCREEN TEXT", result)
        self.assertNotIn("\\n\\n", result)

    def test_malay_voiceover_is_localized_and_has_hook_demo_cta(self):
        result = self.creative_settings({
            "prompt_language": "Malay",
            "prompt_voiceover_mode": "ai",
        })
        self.assertIn("Bahasa Melayu Malaysia", result)
        self.assertIn("Indonesian accent and Indonesian vocabulary are prohibited", result)
        self.assertIn("spoken, product-specific hook", result)
        self.assertIn("spoken CTA", result)
        self.assertIn("NO GENERATED ON-SCREEN TEXT", result)
        self.assertIn("background music clearly below the voice", result)

    def test_no_voiceover_still_prohibits_generated_text(self):
        result = self.creative_settings({
            "prompt_language": "none",
            "prompt_voiceover_mode": "none",
        })
        self.assertIn("No spoken dialogue or voiceover", result)
        self.assertIn("NO GENERATED ON-SCREEN TEXT", result)


if __name__ == "__main__":
    unittest.main()
