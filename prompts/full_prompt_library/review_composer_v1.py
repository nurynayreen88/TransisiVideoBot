"""Review-only Klippo standalone prompt composer. Not wired into the live bot.

Use a single creative concept and explicit user choices, rather than duplicating
the library by ethnicity or age. The caller supplies an actual age range.
"""
from __future__ import annotations

import re

VOICE_TYPES = ("model_speech", "background_narration", "none")
AGE_RANGES = ("child", "teen", "young_adult", "adult", "senior")
PET_SPECIES = ("cat", "dog", "bird", "fish", "rabbit", "hamster", "other")

class PromptChoiceError(ValueError):
    pass

def compose_review_prompt(record: dict, *, product_name: str, human_model: bool,
                          age_range: str | None, voice_type: str,
                          animal: str | None = None) -> dict:
    """Return independent 10s or two continuous 10s prompts for review.

    The creative record's human-model configuration must match the choice;
    choose another concept record rather than silently adding/removing a model.
    """
    if not product_name.strip():
        raise PromptChoiceError("Product name is required")
    if voice_type not in VOICE_TYPES:
        raise PromptChoiceError("Unknown voice selection")
    if human_model != (record.get("model") != "none"):
        raise PromptChoiceError("Select a concept with matching human-model setting")
    if human_model and age_range not in AGE_RANGES:
        raise PromptChoiceError("Select an age range for the human model")
    if not human_model and voice_type == "model_speech":
        raise PromptChoiceError("Model speech requires a visible human model")
    if voice_type != record.get("voice_type"):
        raise PromptChoiceError("Select a concept with matching voice type")
    if animal is not None and animal not in PET_SPECIES:
        raise PromptChoiceError("Unsupported animal category")
    if record.get("subcategory_id", "").startswith("pet_") and animal is None:
        raise PromptChoiceError("Pet product requires an animal")
    duration = record.get("duration_seconds")
    if duration not in (10, 20):
        raise PromptChoiceError("Duration must be 10 or 20 seconds")
    fields = ("full_prompt",) if duration == 10 else ("part_1", "part_2")
    prompts = []
    for field in fields:
        raw = record.get(field)
        if not isinstance(raw, str) or not raw.strip():
            raise PromptChoiceError("Missing standalone prompt part: " + field)
        rendered = raw.replace("{{PRODUCT_NAME}}", product_name.strip())
        rendered = rendered.replace("{{MODEL_AGE_RANGE}}", age_range.replace("_", " ") if human_model else "")
        if animal is not None:
            rendered += (" ANIMAL: A real " + animal + " is clearly visible, "
                         "safely and naturally using the reference pet product; "
                         "species-appropriate behavior and realistic scale. "
                         "A human presenter never replaces the animal.")
        if re.search(r"\{\{[^}]+\}\}", rendered):
            raise PromptChoiceError("Unresolved template placeholder")
        prompts.append(rendered)
    return {"duration_seconds": duration, "voice_type": voice_type,
            "human_model": human_model, "age_range": age_range if human_model else None,
            "animal": animal, "prompts": prompts}
