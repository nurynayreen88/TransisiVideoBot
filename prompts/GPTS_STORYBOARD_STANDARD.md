# Klippo — GPTs Premium Product Storyboard Standard

## Purpose
Generate a production-ready product-video storyboard, not a generic prompt that merely swaps the product name. Every concept must be appropriate to its product category, have a clear visual hook, one coherent signature action, a meaningful detail insert, and a clean closing frame.

## Required output contract
- Exactly 10 seconds, vertical 9:16.
- Four timed beats: 0–2s opening hook; 2–6s signature action; 6–8s detail insert; 8–10s final hero.
- Every beat includes: shot purpose, framing, camera movement, lighting/setting, product/person movement, and continuity/safety constraints.
- No on-screen text, subtitles, captions, added logos or watermark unless the user explicitly asks.
- No dialogue or voice-over by default. If supported, use subtle instrumental music below natural ambience.
- One cohesive ad. Camera cuts must feel motivated; no random location, outfit, actor or lighting changes.

## Product truth / reference lock
Treat a supplied product photo as the source of truth. Preserve visible shape, silhouette, colour, proportions, packaging, parts, fasteners, label placement and markings. Do not hallucinate hidden features, material composition, ingredients, capacity, specifications, compatibility, included accessories or performance/health claims. If a movement is impossible for the actual item, do not force it; replace it with a camera move across a visible detail. Never alter the product to fit the concept.

## Category-specific action rules
- **Clothing / hijab:** show fit, drape, silhouette, sleeve/collar/hem or fabric movement that is visible. Keep the same outfit and person; no outfit morphing.
- **Bags / wallets:** actions may include lifting an existing handle, adjusting a visible strap, turning the item, operating an actual closure, or showing a real visible interior. Never invent pockets or capacity.
- **Shoes:** keep shoes grounded; use a natural step, turn, lace/strap adjustment or outsole/upper detail only when applicable. No impossible sole bending or unsupported grip/comfort claims.
- **Beauty / skincare:** show package, cap, pump, dropper, applicator or plausible small texture/application action. No invented ingredients, skin transformation, medical effects or replacement packaging text.
- **Gadgets / electronics:** show only real visible controls, ports, screen and components. Any button press or screen response must be plausible and consistent; never invent functions or interface text.
- **Food / drink:** keep ingredients and serving quantity grounded in the reference/product name. Pouring, opening, cutting or serving must suit the item and obey realistic liquid/food physics.
- **Home / kitchen / furniture:** demonstrate only real mechanisms and plausible scale. Drawers, lids, switches, hinges or moving parts may move only if present. Keep room layout and furniture geometry consistent.
- **Stationery / crafts:** show a real use action, material detail or careful arrangement. Avoid readable generated writing and prevent tools/materials from multiplying.
- **Sports / outdoor / garden:** use safe, plausible handling and environments. Do not invent performance claims or show hazardous use.
- **Travel / automotive:** show the product in a believable context; keep vehicles stationary during interaction. Do not invent compatibility, compartments or safety claims.
- **Pets / baby:** stage calm, safe interactions only. Never force an animal or child into an unsafe or unnatural pose; avoid unsupported safety or health claims.
- **Accessories / jewellery / watches:** show a real fastening, placement, dial, clasp or visible surface. Do not add stones, components or materials.

## Distinctiveness rules
1. Each library entry needs a genuinely different signature action or visual idea within its category, not just a different camera preset.
2. Do not repeat the same action across multiple entries in the same category unless the creative objective is meaningfully different.
3. A camera move is not a substitute for a product action. The action and camera choreography must work together.
4. The label, description, video prompt and storyboard must describe the same concept.
5. Use the product name as the variable. Keep the concept, sequence, action and camera plan fixed for that library entry; do not rewrite them generically around every product.
6. Avoid vague instructions such as “show the product beautifully”, “make it premium” or “rotate it” unless accompanied by exact framing, direction, speed, focus target and reason for the move.

## Storyboard writing pattern
For each beat specify:
- **Framing:** full product, medium, macro/detail, three-quarter, overhead, eye-level, etc.
- **Camera:** locked-off, slow slider, controlled push-in, small orbit, tilt, or motivated follow; specify direction and restraint.
- **Action:** exactly what the hand/person/product does, how many times, and what must remain unchanged.
- **Light/environment:** plausible and consistent with category and product surface.
- **Continuity:** preserve product identity, hand count, grip, components, shadows, setting and direction of motion.
- **Purpose:** why this beat helps the viewer understand or desire the product.

## Quality gate before saving a prompt
Reject or rewrite an entry if any answer is “no”:
- Does the action make physical sense for this exact category and product?
- Is the opening visually legible within two seconds?
- Is the signature action concrete and distinct from other prompts in the same category?
- Does the detail shot feature something that is actually visible or explicitly supplied?
- Does the final frame clearly show the product and allow the movement to settle?
- Do the description, full prompt and four storyboard beats agree?
- Are unsupported claims, fake label text, extra accessories, morphing and impossible movement excluded?
- Is the camera move precise, motivated and achievable in ten seconds?

## Canonical output skeleton
**0–2s — Opening hook:** Establish the full product and context. State the framing, light and first camera move. Make the product recognisable immediately.

**2–6s — Signature action:** State one exact action in sequence. Specify who/what moves, direction, speed and number of repetitions. Add a camera move that supports the action, not distracts from it. Preserve product identity.

**6–8s — Detail insert:** Show one real, category-relevant detail. Specify focus target and a brief stable movement. Do not invent hidden features or readable text.

**8–10s — Hero finish:** Return to a complete product view. Let movement settle, preserve the original design and hold a clean final composition.

## Important
A large library is not automatically a high-quality library. Prefer fewer, clearly differentiated, category-correct concepts over inflated counts of near-duplicates. Audit semantic repetition, not only duplicate IDs or JSON validity.
