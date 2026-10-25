# Klippo standalone full-prompt rules v3

This is a non-destructive review specification. Existing prompt files, IDs and cookware records remain intact. Do not activate or merge the review batch until content quality passes.

## User selections
- Human model: one type only, **Universal Malaysian model**. No race/ethnicity selection. Human model ON/OFF remains selectable.
- Age: retain a user-selectable age range. Apply the selected age directly to the final prompt. Adults present adult products; children’s products use age-appropriate, safe and tasteful scenes.
- Voice: **Model speech** (natural Malaysian Malay, accurate lip sync), **Background narration** (natural Malaysian Malay; human model stays silent), or **No voice** (music/ambience only). Model speech is unavailable with human model OFF.
- Pet-related products: the relevant animal MUST appear and demonstrate credible product use. A human model may also appear according to the human-model selection; never substitute the human for the animal.
- Duration: 10 seconds is one complete storyboard; 20 seconds is two distinct, continuous 10-second prompts with matching product, setting and visual continuity.
- Preset, camera, lighting, setting, action and audio are explicit in each emitted prompt.

## Generation rules
- Store one high-quality, subcategory-specific concept as the base. Compose a **complete, self-contained final prompt** using the user’s model, age, voice, preset and duration choices; avoid duplicating concepts by race/model type.
- Never output conditional branches such as `if`, `optional`, `otherwise`, `when selected` or `substitute` in the final video prompt.
- Model speech includes the actual Malaysian Malay spoken line, speaker, on-screen action and lip-sync instruction. Background narration includes its actual distinct Malay line and explicitly keeps any human model silent. No-voice output contains no dialogue or narration.
- Animal behavior and product contact must be safe, natural and species-appropriate. Do not invent visible product features, accessories, material claims, zippers, hardware or fit details not supported by the uploaded reference.
- Every concept requires a unique setting, substantive product-specific action, camera plan and distinct voice line. Repeating one generic storyboard across records fails review.
- Keep the reference product's design, color, proportions and identity unchanged. Use a realistic vertical 9:16 presentation.
- For 20 seconds, Part 1 and Part 2 must each be complete generation prompts, with different shots and dialogue but a connected story.

## Quality gate before merge
Audit all 100 records for ID uniqueness, correct duration and metadata, 10 subcategory coverage, voice/model compatibility, age choices, pet-animal presence, distinct settings/actions/dialogue, realistic use, prohibited conditional wording and 20-second continuity. Keep PR in draft and do not deploy Render until this audit passes.
