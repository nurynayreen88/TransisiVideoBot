# V8 model visibility policy (review only)

Most practical product demonstrations should use a visible human model. This policy does not delete or silently relabel earlier V6/V7 variants.

## Visual categories

1. **FULL_MODEL** — a visible Universal Malaysian adult demonstrates real product use. Model age is selected only in this category. Voice may be visible model speech in natural Malaysian Malay with synchronized lips, off-camera Malaysian Malay narration while the model stays silent, or music only.
2. **HANDS_ONLY** — only a person's hands and a limited forearm may appear for believable product handling; no face, torso, body silhouette, or visible lips. Voice is off-camera Malaysian Malay narration or music only. Hands-only is a real human interaction, never classified as product-only.
3. **PRODUCT_ONLY** — no human, hands, human silhouette or invisible manipulation. Product remains in a physically plausible state. Animal products may show the actual animal without a human; classify separately as ANIMAL_ONLY when appropriate.

## Selection

- Prefer FULL_MODEL for apparel, wearable items, beauty application, bags and practical use where a full person is needed.
- Prefer FULL_MODEL or HANDS_ONLY for cooking, filling a bottle, writing, packing, operating a device and comparable tactile demonstrations.
- PRODUCT_ONLY is for credible static product views, realistic before/after arrangements without unexplained transitions, and cases where use is visible without human interaction.
- Pet demonstrations must include the relevant animal. FULL_MODEL + ANIMAL or ANIMAL_ONLY are valid; HANDS_ONLY + ANIMAL requires a safe, visible interaction.
- Do not output model age choices for HANDS_ONLY, PRODUCT_ONLY or ANIMAL_ONLY.
- Every creative concept is stored as its own complete prompt per valid visual/voice combination and duration (10s and continuous 20s as two complete 10s parts). AUDIO remains the final instruction in each prompt/part. No conditional language inside final prompts.

## Review migration

Older V7 variants labelled no-model that require human handling are REVIEW_BLOCKED until a complete HANDS_ONLY or FULL_MODEL replacement is authored and validated. Preserve their old IDs for audit and use new IDs for replacement variants. Do not activate V8 automatically, merge PR #157, or deploy Render.
