# Klippo — Subcategory Variation Library Audit

**Audit type:** Structural coverage and runtime-wiring check  
**Branch:** `main`  
**Scope:** Additive variation library; existing master prompts and video engine are preserved.

## Coverage result

- Product subcategories in the existing canonical component table: **130**
- Curated variation bundles added: **1300**
- Minimum per subcategory: **10**
- Required components in each variation: hook, product-safe action, visible-detail focus, camera direction, lighting direction, closing hero direction and audio guidance.
- Library file: `prompts/subcategory_variation_library.json`
- Runtime: `prompt_engine.py` loads the library and selects a variation using the exact selected subcategory ID when available. It avoids repeating the last three choices for that subcategory.
- Existing master library: `prompts/prompt_library.json` remains unchanged.
- Existing additive quality overrides and fal.ai video-generation engine remain unchanged.

## Subcategory counts

| Existing category ID | Subcategories | Variations |
|---|---:|---:|
| `fashion` | 8 | 80 |
| `bag` | 8 | 80 |
| `hijab` | 7 | 70 |
| `shoes` | 7 | 70 |
| `beauty` | 7 | 70 |
| `food` | 7 | 70 |
| `gadget` | 7 | 70 |
| `home` | 8 | 80 |
| `accessory` | 7 | 70 |
| `toy` | 7 | 70 |
| `book_stationery` | 7 | 70 |
| `sports` | 8 | 80 |
| `pet` | 7 | 70 |
| `automotive` | 7 | 70 |
| `baby` | 7 | 70 |
| `travel` | 7 | 70 |
| `office` | 7 | 70 |
| `other` | 7 | 70 |

## Product/model safeguards

- Variations do not force a human, child or animal model; they follow the user's model selection and the existing model-safety rules.
- Product shape, colour, markings, proportions and supplied parts remain locked to the reference.
- Actions are conditional: if the reference does not support a physical interaction, simplify to a safe camera/detail reveal.
- No invented product features, ingredients, materials, claims, prices, accessories or on-screen text.

## Prompt flow changes

The main `Jana Prompt` path now follows this order:

1. Category
2. Subcategory
3. Product name
4. Model selection (human; animal where relevant; or product-only)
5. Model details, when a model is selected
6. Video style
7. Duration
8. Ad angle, on-screen text and audio/voice options
9. Scene and camera direction
10. Prompt confirmation and generation

The selected subcategory is retained after the product name is entered so it can drive the variation-library lookup. The chosen model and style are not overwritten when duration is selected.

## Verification boundary

The automated checks verify library coverage, distinct variation IDs/actions, and the prompt-flow ordering. This is a structural audit, not a claim that all 1,300 variations have been manually judged or that generated video output has been visually tested. External video models may interpret directions differently.
