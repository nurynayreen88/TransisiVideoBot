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

    if child_product and category in {"fashion", "shoes"}:
        return {
            "prompt_model_presence": "yes",
            "prompt_model_count": 1,
            "prompt_model_gender": "auto",
            "prompt_model_hijab": "na",
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
