# V9 cross-file QA gate — 24 October 2026

Scope: five V9 JSON files on PR #157 staging branch, reviewed against source records without deleting or activating any existing batch.

## Verified structural results
- 70 records, 70 unique IDs across all five files; 35 10-second records and 35 20-second records.
- Voice metadata: 60 BACKGROUND_NARRATION, 4 MODEL_SPEECH, 6 NO_VOICE.
- No occurrences of forbidden conditional tokens `if`, `otherwise` or `optional` in final prompt text.
- No MODEL_SPEECH record is assigned to a non-FULL_MODEL visual category.

## Creative quality gate — BLOCKED
1. The first 30 pilot records in `v9_partial_model_pilot_01.json` and `v9_multicategory_pilot_02.json` use generic storyboard timing/action wording. Retain for audit but mark as supersession candidates, not release-ready.
2. The 30 records in creative rewrite 01/02 are better product-specific alternatives, but still require human review of timing, natural Malaysian Malay dialogue, hooks, CTAs and whether each second part meaningfully advances rather than repeats Part 1.
3. The 10 voice-diversity records add actual model speech and no-voice paths; review lip-sync timing and visible-mouth framing before release.
4. Overall voice coverage remains skewed: 60 background narration, 4 model speech, 6 no voice. This is an observed count, not a target distribution.
5. Placeholder `{{PRODUCT_NAME}}` requires explicit substitution and reference-image grounding before user-facing emission. No final prompt should expose unresolved placeholders.
6. The current 20-second records are stored as two separately described continuous 10-second generation prompts. Validate continuity shot by shot with the intended video provider before activation.

## Required next work
- Replace generic pilot concepts non-destructively with complete category-specific storyboards; maintain old IDs for traceability and assign new IDs to replacements.
- Add distinct product-specific hooks, actions and endings; avoid repeating a generic 0–2 / 2–5 / 5–8 / 8–10 template as a substitute for creative differentiation.
- Expand valid model speech and no-voice variants, with lip-sync only where the model's mouth is visible. PARTIAL_MODEL, HANDS_ONLY and ANIMAL_ONLY must not claim visible model speech.
- Pet-product scenes must contain the relevant animal with safe natural interaction.
- Do not merge PR #157, activate the engine or deploy Render until full QA passes.
