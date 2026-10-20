"""Conservative automatic model defaults for Klippo product prompts."""


def auto_prompt_model_defaults(product_type, product_subcategory="", child_product=False, animal_related=False):
    """Choose a safe, category-fit default without guessing product-specific facts."""
    category = str(product_type or "other").casefold()
    subtype = str(product_subcategory or "").casefold()

    if animal_related or category == "pet":
        return {
            "prompt_model_presence": "animal",
            "prompt_model_count": 1,
            "prompt_model_gender": "none",
            "prompt_model_hijab": "na",
            "prompt_model_ethnicity": "na",
            "prompt_model_age": "na",
            "prompt_animal_species": "auto",
        }

    if child_product and category in {"fashion", "shoes", "hijab"}:
        is_hijab_product = category == "hijab"
        return {
            "prompt_model_presence": "yes",
            "prompt_model_count": 1,
            "prompt_model_gender": "female" if is_hijab_product else "auto",
            "prompt_model_hijab": "hijab" if is_hijab_product else "na",
            "prompt_model_ethnicity": "random_malaysia",
            "prompt_model_age": "8-12",
            "prompt_animal_species": "auto",
        }

    if category in {"fashion", "hijab", "shoes"}:
        if subtype == "fashion_men":
            gender = "male"
        elif subtype in {"fashion_women", "fashion_dress", "hijab_bawal", "hijab_shawl", "hijab_instant", "hijab_sport"} or category == "hijab":
            gender = "female"
        else:
            gender = "auto"
        return {
            "prompt_model_presence": "yes",
            "prompt_model_count": 1,
            "prompt_model_gender": gender,
            "prompt_model_hijab": "hijab" if category == "hijab" else "na",
            "prompt_model_ethnicity": "random_malaysia",
            "prompt_model_age": "26-40",
            "prompt_animal_species": "auto",
        }

    return {
        "prompt_model_presence": "none",
        "prompt_model_count": 0,
        "prompt_model_gender": "none",
        "prompt_model_hijab": "na",
        "prompt_model_ethnicity": "na",
        "prompt_model_age": "na",
        "prompt_animal_species": "auto",
    }

def image_model_direction(user_data, child_product=False):
    """Describe the selected human/animal model consistently for an image prompt."""
    presence = str(user_data.get("prompt_model_presence", "none")).casefold()
    if presence == "animal":
        species = str(user_data.get("prompt_animal_species", "auto")).casefold()
        labels = {
            "auto": "only an animal species clearly supported by the product name/reference; if unclear, do not invent a species",
            "cat": "one cat",
            "dog": "one dog",
            "rabbit": "one rabbit",
            "bird": "one bird",
            "hamster": "one hamster",
            "fish": "one fish",
            "horse": "one horse",
        }
        return (
            "Include " + labels.get(species, labels["auto"]) +
            " only when it suits the product. Keep the animal calm and anatomically natural; "
            "show no forced tricks, distress, unsafe handling or unsupported product claims."
        )

    if presence != "yes":
        return "No human or animal model. Focus entirely on the exact product."

    age = str(user_data.get("prompt_model_age", "26-40"))
    gender = str(user_data.get("prompt_model_gender", "auto")).casefold()
    gender_text = {
        "female": "female",
        "male": "male",
        "auto": "matching the product/reference; if unclear, use neutral natural styling",
    }.get(gender, "matching the product/reference")
    count = min(2, max(1, int(user_data.get("prompt_model_count", 1) or 1)))

    if age in {"4-7", "8-12", "13-17"}:
        if not child_product:
            return "Do not show a child or teen model; focus on the product and use adult hands only if needed."
        return (
            f"Include {count} child/teen model(s), age {age}, gender presentation {gender_text}. "
            "Keep the model's appearance consistent, use age-appropriate styling and natural safe actions, "
            "and preserve the product's exact visible design."
        )

    if child_product:
        return (
            f"Include {count} adult model(s), gender presentation {gender_text}, age {age}, only as a presenter. "
            "Do not dress the adult in child-sized clothing or footwear; show the item on a suitable hanger, "
            "mannequin or surface, with the adult presenting it naturally."
        )

    return (
        f"Include {count} adult model(s), gender presentation {gender_text}, age {age}. "
        "Keep face, styling and outfit consistent; for clothing, wear the exact reference garment without redesign."
    )

