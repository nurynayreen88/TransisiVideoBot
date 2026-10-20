# Klippo Prompt Audit — Technical Review

Date: 2026-10-20  
Scope: source-level review of `main` snapshot; audit report only. No production code or database changed.

## Executive finding

The most important issue is not simply that some prompt text is long. The generator **throws away most of the selected directions by slicing them to fixed character counts**. The stored library can be detailed, but the final prompt may contain only a short fragment. This is a confirmed source-level defect and should be fixed before polishing individual style descriptions.

## Confirmed findings

| Priority | Area | What the source shows | Why it matters | Recommended correction |
|---|---|---|---|---|
| Critical | Prompt assembly / truncation | In the standard storyboard output, style template is cut at 70 characters, setting at 100, camera at 70 and creative idea at 100. A universal framework preview is also cut at 180 characters in another prompt component. | Important instructions can be lost; sentence fragments such as “No capacity, durability or security…” can weaken or confuse the model. | Replace raw slicing with a semantic summary or retain the first complete sentence even when slightly over the nominal limit. The current candidate helper is not sufficient: e.g. a long first sentence can be replaced by a generic fallback. Add tests confirming each selected style keeps its distinctive direction. |
| High | Universal framework lookup | `luxury_reveal`, `zoom` and `detail_macro` are referenced by the JSON framework but are not keys in `STYLES`. Unknown keys fall back to the first framework. | The output may silently receive a premium framework when a camera/detail framework was intended. | Create an explicit alias map to canonical styles or define the missing styles. Make unknown keys visible in tests rather than silently falling back. |
| High | Hook variety | Many category hooks use generic patterns such as “TENGOK BEG INI” and “TENGOK KASUT INI”. | Repeated openings reduce variety and can feel formulaic. | Add curated Malay Malaysia hooks by category and ad angle; never invent benefits, popularity, discounts, price or urgency. |
| High / requires full-path check | Spoken language | The builder accepts `prompt_language`, but the visible final suffix generically instructs Malay speech. Confirm how callers and any other prompt branches apply the selected language. | English voice mode may conflict with a generic Malay instruction if the selected language is not propagated through every path. | Separate technical prompt language from spoken-audio language and test both modes end to end. |
| Medium | Style, camera and action overlap | Camera direction, style template, category action and scene beat are assembled separately; each may prescribe push-ins, slides, tracking or close-ups. | More than one move can be requested for the same beat, despite the intended restrained camera direction. | Define distinct roles: style = visual look, camera = one move, action = subject movement. Combine into each beat and test for conflicts. |
| Medium | Category action/audio coverage | Creative actions and SFX are grouped into 10 profiles, while the product taxonomy has more categories. Some categories fall into broader groups. | A toy, travel item, jewellery, garden product or baby item can receive generic action/audio rather than category-appropriate guidance. | Map every supported category intentionally; keep a clearly defined generic fallback. SFX must match visible action and stay below speech. |
| Medium | Doodle and text rules | Global rules prohibit unrequested text, while the white-doodle paths contain optional language allowing verified hook/feature labels. | A video may show text when the user expected only animated doodles, or the blanket rule may suppress selected overlays. | Treat doodle graphics and text as separate features. Text should appear only when explicitly enabled and sourced from verified content. |
| Medium | Scene coverage | Detailed five-beat templates exist for selected categories; many others rely on generic fallback scenes. | Videos can share the same structure even when the product category needs a different physical action. | Add category-specific beats where they improve realism; avoid adding templates merely for quantity. |
| Medium | Prompt duplication | Product identity, category guardrails, motion, framing, scene actions, style, storyboard and creative variation repeat some constraints. | Repetition increases prompt length and may create conflicting priorities. | Compose in a hierarchy: product lock → style → five timed beats → one action/camera move per beat → selected voice/audio → concise negative constraints. |
| Medium | Multi-clip continuity | Part numbering and continuity rules are distributed across the builder and creative variation function. | 20s/30s prompts can repeat an opening or mismatch the intended handoff if part numbering diverges across branches. | Standardize part numbering and add regression tests for 2- and 3-part outputs. |

## Important limits on these findings

- This is a source review, not a live production database dump.
- The active SQLite file is configured through `KLIPPO_PROMPT_DB`. Since production rows were not read, existing customized or older rows may differ from source defaults.
- The three missing framework keys could be intentional aliases. The lookup behavior is confirmed; whether the missing names are a product decision or a defect needs explicit mapping.
- Language selection needs end-to-end verification through callers and generated output before labelling it a production failure.
- A prompt can be syntactically valid and still produce a poor video; category/style quality requires generated-output tests, not only static inspection.

## Recommended fix order

1. **Fix sentence-aware prompt assembly and stop discarding most style/camera/setting direction.**
2. **Resolve missing framework keys explicitly and add a test that catches unknown keys.**
3. **Test category/subcategory routing**, especially handbag vs wallet vs backpack, using Malay and English product names.
4. **Verify selected spoken language end to end** and separate speech, music and SFX instructions.
5. **Unify the camera/action/storyboard composition** so each beat has one clear action and at most one camera move.
6. **Improve hooks and fill category scene gaps** only after the generation logic is stable.
7. **Compare the production SQLite rows** against source defaults read-only before deciding whether the live catalog needs a migration.

## Regression test matrix

| Input | Expected result |
|---|---|
| Bonia handbag | Handbag presentation; no “wallet” language or wallet-only claims |
| Bonia wallet / card holder | Wallet presentation; no invented card slots, cash or capacity |
| Laptop backpack | Upright backpack framing; no assumed laptop sleeve or compartments |
| Child's clothing / shoes | Age-appropriate model choice verified through the upstream model selector |
| Adult men's clothing | Adult male model choice verified through the upstream model selector |
| English spoken voice | Original source had conflicting Malay-only opening/hook text; patched separately in PR #131; regression tests pass |
| Malay spoken voice | Natural Bahasa Melayu Malaysia; no Indonesian phrasing or unintended language mixing |
| White Doodle, text disabled | Animated graphic lines only; no random labels/captions/logos |
| White Doodle, text explicitly enabled | Only verified user-provided/approved text; graphics do not obscure product |
| 20-second output | Two connected 10-second prompts; second prompt continues without repeating hook |
| 30-second output | Three connected parts with consistent numbering and no repeated opening |
| Long custom setting/style | Complete meaningful sentences; no mid-sentence fragments |

## Files

- [Full inventory](full_inventory.csv)
- [Styles](styles.csv)
- [Category/subcategory mapping](category_subcategory_map.csv)
- [Framework key check](framework_style_key_check.csv)
- [Detailed findings table](audit_findings.csv)

This inventory branch contains audit/report files only. Prompt fixes are kept in separate PR #131, which remains open and has not been merged or deployed.

## Implementation progress

PR #131 is open for review and has not been merged or deployed. It addresses lossy first-sentence summaries in style/scene/camera/concept, truncated camera-framing selections, camera/style conflicts, script-vs-auto-hook conflicts, explicit bag-subcategory precedence, baby-product model age suitability, single-model head-covering consistency, universal framework key mismatches and duplicate styles, English/Malay opening and hook consistency, use of curated category hook rows, five-beat scene coverage for all top-level product categories, and White Doodle continuity. Latest GitHub Actions checks passed on head `915610e142ed2dcd3fd15fe74bb37a286bbd4bab`: prompt quality regression tests (run #35) and Klippo prompt library checks (run #507), including Python syntax, prompt regression tests, category coverage, Auto-style key validation, full style/scene/camera/concept preservation, script-priority wording, complete camera-framing directions, explicit bag-subcategory precedence and baby-product model suitability.

Still outstanding: compare production SQLite prompt rows read-only; audit model selection end to end; review existing/custom hook rows; and inspect generated outputs across styles for camera/action conflicts. Do not merge or deploy without explicit approval.
