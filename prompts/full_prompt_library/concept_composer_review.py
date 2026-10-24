"""Concept-first prompt composition prototype, isolated from production."""
from __future__ import annotations

try:
    from .voice_layer_review import add_voice_to_complete_concept, available_voice_choices
except ImportError:
    from voice_layer_review import add_voice_to_complete_concept, available_voice_choices


def compose_concept(concept, product_name, duration, human_model, age_range, voice,
                    dialogue_1="", dialogue_2="", animal=None):
    if duration not in (10, 20):
        raise ValueError("Unsupported duration")
    if not product_name or not product_name.strip():
        raise ValueError("Product name required")
    if human_model and not age_range:
        raise ValueError("Model age required")
    if not human_model and age_range:
        raise ValueError("Age only applies to a human model")
    if voice not in available_voice_choices(human_model):
        raise ValueError("Incompatible voice selection")
    category = concept["category"]
    if category.startswith("pet_") and not animal:
        raise ValueError("Pet products require a verified animal")
    if not category.startswith("pet_") and animal:
        raise ValueError("Animal only applies to pet products")
    required = ("setting", "action", "camera", "lighting", "opening",
                "development", "finish", "continuation", "second_development",
                "second_finish")
    if any(not concept.get(key) for key in required):
        raise ValueError("Incomplete creative concept")
    subject = ("One Universal Malaysian model aged " + age_range.replace("_", " ") +
               " naturally presents the actual product. " if human_model else
               "Product-only display without any human model or hands. ")
    pet = ("A real " + animal + " stays visible and safely uses the actual product. "
           if animal else "")
    base = ("Vertical 9:16, realistic 4K. Product: " + product_name.strip() +
            ". CONCEPT: " + concept.get("id", category) + ". LOCATION: " +
            concept["setting"] + ". SUBJECT: " + subject + pet + "ACTION: " +
            concept["action"] + ". CAMERA: " + concept["camera"] +
            ". LIGHTING: " + concept["lighting"] +
            ". Keep exact reference colour, design, details and proportions. "
            "No invented accessories, captions, logos or watermark. ")
    first = (base + "STORYBOARD 0–3s: " + concept["opening"] +
             " 3–7s: " + concept["development"] + " 7–10s: " +
             (concept["continuation"] if duration == 20 else concept["finish"]))
    result = [add_voice_to_complete_concept(first, voice, human_model, dialogue_1)]
    if duration == 20:
        second = (base + "PART 2: Continue the exact final frame of Part 1 with the "
                  "same product, setting, lighting and subjects. 0–3s: " +
                  concept["continuation"] + " 3–7s: " +
                  concept["second_development"] + " 7–10s: " +
                  concept["second_finish"])
        result.append(add_voice_to_complete_concept(second, voice, human_model, dialogue_2))
    return result
