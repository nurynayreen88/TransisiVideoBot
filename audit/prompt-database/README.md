# Klippo Prompt Database Audit — source inventory

Generated: 2026-10-20

## Scope and caveat
This is a structured inventory extracted from the current `main` source files, not a direct export of the production SQLite database. The live runtime catalog is loaded via `KLIPPO_PROMPT_DB` / `prompt_catalog.py`; the actual database file and production environment value were not available to read in this audit. Therefore, treat these tables as the repository's source-defined prompt library and review them before calling this a verified live-database dump.

## Source snapshot
- `prompt_catalog.py` blob SHA: a2b634a51c69f38094c28fdca1aacc8d75ea95ac
- `prompt_engine.py` blob SHA: e03e274a4f08bbad7fe8997c0e20fc01c8837022
- `prompts/universal_prompt_templates.json` blob SHA: 6350a3c07125b7df1faf8a3960d673fcbc8c39d6
- Branch audited: `main`

## Files
- [Styles](styles.csv): full style names and prompt directions.
- [Category/subcategory map](category_subcategory_map.csv): Auto style categories and explicit bag/wallet/backpack subtype conditions.
- [Cameras](cameras.csv): camera movement directions.
- [Creative actions](creative_actions.csv): category-specific actions.
- [Category scene beats](category_scene_beats.csv): scene beats for categories with specific templates.
- [Audio/SFX](audio_sfx.csv): category sound-effect directions.
- [Auto style mapping](auto_style_mapping.csv): ordered style candidates per category.
- [Creative angles](creative_angles.csv): question, reveal, demo, relatable, premium and affiliate approaches.
- [Category directions](category_directions.csv): full product category guardrails.
- [Natural motion](natural_motion.csv): movement guidance by category.
- [Framing priorities](framing_priorities.csv): category-specific framing instructions.
- [Category hooks](category_hooks.csv): keyword-to-hook mappings.
- [Opening variations](opening_variations.csv): visual, camera and voice opening variation libraries.
- [Universal frameworks](universal_frameworks.csv): style-to-framework mapping and directions.
- [Universal rules](universal_rules.csv): global product and prompt constraints.
- [Audit findings](audit_findings.csv): preliminary findings and proposed review points.

## How to review
1. Check whether each product subcategory is assigned the correct product type and style candidates.
2. Mark which component directions should be shared across categories versus remain category-specific.
3. Check that every style key referenced by a framework exists or is an intentional alias.
4. Confirm that hook, camera, action, sound, product-lock and no-unrequested-text rules do not conflict.
5. Before implementation, compare this source inventory against the actual active rows in the production SQLite database.

## Important
No app code was changed by this report. This branch contains audit artifacts only; it is not deployed and should not be merged into production as a code fix.
