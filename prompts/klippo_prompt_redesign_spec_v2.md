# Klippo Prompt Redesign Specification v2

Status: canonical design brief for rebuilding prompt variations. This document does not replace or delete the existing prompt library. The existing library remains a reference and rollback source until rebuilt prompts pass validation.

## Product flow

1. User selects one of the eight existing presets:
   - Cinematic
   - Minimal
   - Lifestyle
   - Dynamic
   - Luxury
   - Flatlay
   - Creative Reveal
   - White Doodle
2. Immediately after preset selection, user selects a location from a preset-appropriate list. Include a clearly labelled "Other location" option for user-entered locations.
3. Klippo selects/builds a creative route that fits the selected preset, selected location, product category, reference image, and user-selected model/audio settings.
4. Klippo composes one complete prompt and sends it through the existing generation flow. Do not create a second prompt mode or change the fal.ai engine as part of prompt redesign.

## Non-negotiable location rule

The location is user-controlled. Never silently replace it with a different place. Every route must honor the exact selected location and describe a plausible scene within it. If the user enters a custom location, preserve its meaning and do not substitute a preset location.

## Scene coherence rules

Every prompt must be internally consistent across:
- location and environment;
- time of day and available/practical light sources;
- lighting style and shadows/reflections;
- surfaces, background objects, weather, and atmosphere;
- product interaction and physical action;
- camera angle/movement and available space;
- details, reveal, and closing frame;
- audio and visible action.

Do not add environmental details merely for decoration. Do not describe a neon-lit studio setup in a sunlit garden unless the scene explicitly and plausibly includes such lighting. Avoid incompatible combinations (for example, outdoor daylight plus unexplained studio-only reflections, rain/wet surfaces without rain, fog without a plausible setting, or a product interacting with props not present in the scene).

A preset describes the creative treatment, not permission to contradict the location. Preserve the preset's identity while adapting lighting and staging to the selected place.

## Eight preset identities

- **Cinematic:** intentional visual storytelling, composed frames, motivated camera movement, dramatic but plausible light.
- **Minimal:** restrained composition, uncluttered scene, limited visual elements, clean movement.
- **Lifestyle:** believable everyday use in a fitting real-world environment.
- **Dynamic:** energetic but physically plausible action and camera movement, without losing product readability.
- **Luxury:** refined composition, controlled highlights, premium pacing; do not claim the product itself is luxury unless supported.
- **Flatlay:** overhead or near-overhead arrangement on a suitable surface; do not force an overhead scene when it makes the product unusable or unreadable.
- **Creative Reveal:** a clear, coherent reveal mechanism grounded in the selected location; avoid magical morphing or unsupported props.
- **White Doodle:** bright, simple scene compatible with white doodle overlays; do not add visible text/logos, and ensure overlays do not obscure product details unless the user explicitly requests that.

## Variation / branching standard

A preset must contain multiple genuinely distinct creative routes. Routes should differ in meaningful creative structure, not only synonyms or camera adjectives. Across a preset, vary suitable combinations of:
- opening hook and visual premise;
- product action or interaction;
- reveal/story progression;
- framing and camera movement;
- focal detail and composition;
- ending/closing image;
- audio treatment when user settings permit.

Variation is bounded by the product reference and selected location. Do not change product identity, invent product features, or force an action the reference/product does not support. Prefer a camera-led reveal when product interaction is unsupported.

## Complete prompt requirements

Each variation must contribute concrete, usable direction for:
- opening/hook;
- action and scene progression;
- product-visible details supported by the reference;
- camera framing and movement;
- lighting compatible with the selected location and time;
- coherent closing frame;
- audio only within the user's selected audio settings.

The location selection must be injected into the final composed prompt as a required scene constraint, even if the existing variation record format does not contain a dedicated location field. Do not assume a location mentioned in a variation overrides the user's selection. If a variation's original wording conflicts with the chosen location, adapt or reject that route before generation.

## Product accuracy and safety

- Preserve visible product identity, shape, colour, pattern, labels, proportions, and supplied parts.
- Never invent features, materials, ingredients, accessories, claims, prices, discounts, or results.
- Keep actions physically plausible and category-appropriate.
- Do not force a human, child, or animal model; follow explicit user selection and applicable safety rules.
- No on-screen text, captions, extra logos, or watermark unless explicitly selected by the user.
- Audio and sound effects must be consistent with visible action and user preferences.

## Validation checklist before a prompt is accepted

1. Does it preserve the selected preset's identity?
2. Does it honor the exact user-selected location?
3. Are lighting, time of day, shadows, reflections, surfaces, props, and atmosphere compatible?
4. Is the action plausible for the product and location?
5. Is the camera direction possible in the described space?
6. Are product details supported by the reference?
7. Is the route meaningfully different from other routes in that preset?
8. Does the closing frame follow naturally from the action?
9. Does audio follow the user's settings and visible scene?
10. Is there any contradiction, unsupported feature, accidental text/logo, or unnecessary scene detail?

Reject or rewrite any variation that fails a check. Do not bulk-replace the existing catalog until the new version has passed structural validation and representative per-category review.

## Migration policy

- Preserve the current `prompts/subcategory_variation_library.json` as the legacy/reference catalog while rebuilding.
- Work in reviewable batches and keep IDs unique.
- Do not alter the existing fal.ai engine, deploy services, or remove old prompt data as part of this prompt redesign.
- After each batch, parse JSON, verify required fields and unique IDs, run contradiction/location checks, and reread the committed file from GitHub.
