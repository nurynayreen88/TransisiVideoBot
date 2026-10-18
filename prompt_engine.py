from prompt_catalog import resolve, product_hook
"""Detailed, reference-safe AI video prompt templates for KLIPPO."""

CAMERAS = {
    "orbit": "A restrained camera arc of at most 30 degrees with subtle parallax. Never reveal or fabricate an unseen side.",
    "push": "A smooth slow dolly-in from a balanced medium product shot to a crisp detail, with no digital warping.",
    "side": "A measured left-to-right lateral camera slide with gentle depth separation and stable product proportions.",
    "static": "A locked premium studio composition with delicate lighting movement and a subtle focus transition.",
}

AUTO_STYLE_BY_PRODUCT_TYPE = {
    # Every selectable product type gets a deterministic category-fit style.
    # Do not fall through to random catalog styles for unlisted categories.
    'fashion': 'fashion_editorial',
    'bag': 'handbag_showcase',
    'wallet': 'wallet_luxury_macro',
    'hijab': 'fashion_editorial',
    'shoes': 'studio_360_safe',
    'beauty': 'beauty_macro',
    'food': 'food_appetite',
    'gadget': 'tech_demo',
    'home': 'cozy_home',
    'accessory': 'luxury',
    'toy': 'playful_viral',
    'book_stationery': 'flatlay',
    'sports': 'pov_demo',
    'pet': 'lifestyle',
    'automotive': 'studio_360_safe',
    'baby': 'cozy_home',
    'travel': 'studio_360_safe',
    'office': 'flatlay',
    'garden': 'nature_fresh',
    'kitchen': 'cozy_home',
    'furniture': 'cozy_home',
    'crafts': 'flatlay',
    'other': 'cinematic',
}


def _resolve_auto_style(style, product_type):
    """Choose a stable, category-appropriate catalog style without an AI call."""
    if style != 'auto':
        return style
    return AUTO_STYLE_BY_PRODUCT_TYPE.get(product_type, 'cinematic')


def build_prompt(mode, product, scene, motion, style='auto', duration=10, concept='', product_type='other', storyboard_override=None, split=None):
    # Preserve the historical API behavior: a 20-second call without an explicit
    # split choice still returns two connected 10-second prompts.
    if split is None:
        split = duration == 20
    style = _resolve_auto_style(style, product_type) if mode == 'storyboard' else style
    if split and duration > 10:
        # Generate connected 10-second prompts while retaining the same style and product context.
        parts = [
            _build_single_prompt(mode, product, scene, motion, style, part=index, duration=10,
                                 concept=concept, product_type=product_type, storyboard_override=storyboard_override)
            for index in range(1, duration // 10 + 1)
        ]
        return "\n\n".join(
            ("=== KLIPPO PART " + str(index + 1) + " ===\n\n" + part) if index else part
            for index, part in enumerate(parts)
        )
    return _build_single_prompt(mode, product, scene, motion, style, part=0, duration=duration,
                                concept=concept, product_type=product_type, storyboard_override=storyboard_override)


def _build_single_prompt(mode, product, scene, motion, style='auto', part=0, duration=10, concept='', product_type='other', storyboard_override=None):
    camera = CAMERAS.get(motion, CAMERAS["push"])
    product_type_directions = {
        'fashion': "PRODUCT CATEGORY DIRECTION: Treat this as clothing/fashion. Favor natural fabric movement and visible garment details; never alter cut, print, color or pattern.",
        'bag': "PRODUCT CATEGORY DIRECTION: Treat this as a bag subtype inferred from the product name. Choose a matching presentation (handbag hero, crossbody lifestyle or backpack upright showcase). Do not assume exact materials, compartments, hardware or accessories unless stated in the name.",
        'wallet': "PRODUCT CATEGORY DIRECTION: Treat this as a wallet inferred from the product name. Favor a luxury macro, simple open-close presentation or clean flat lay. Do not assume exact materials, card slots, coin pockets, compartments or capacity.",
        'hijab': "PRODUCT CATEGORY DIRECTION: Treat this as a hijab/tudung. Emphasize the exact drape, folds, texture and visible styling; do not change the wrap, color or fabric pattern.",
        'shoes': "PRODUCT CATEGORY DIRECTION: Treat this as footwear. Favor grounded placement and visible upper/outsole details; do not invent soles or unseen angles.",
        'beauty': "PRODUCT CATEGORY DIRECTION: Treat this as a beauty, cosmetics or skincare product. Favor clean styling, packaging and texture close-ups; do not imply medical results or unverified benefits.",
        'food': "PRODUCT CATEGORY DIRECTION: Treat this as food or drink. Favor appetizing but realistic lighting and visible texture; do not add ingredients, toppings or serving items not shown.",
        'gadget': "PRODUCT CATEGORY DIRECTION: Treat this as an electronic gadget. Favor precise edges, ports, buttons and screen details only where visible; keep geometry and screen content unchanged.",
        'home': "PRODUCT CATEGORY DIRECTION: Treat this as a home/kitchen product. Favor believable placement and practical scale; do not add components or imply functions not visible.",
        'accessory': "PRODUCT CATEGORY DIRECTION: Treat this as an accessory or jewellery. Favor delicate close-ups, accurate reflections and realistic scale; do not invent stones, engravings or materials.",
        'travel': "PRODUCT CATEGORY DIRECTION: Treat this as travel gear or luggage. Favor believable packing, handling and travel-preparation scenes; do not invent capacity, locks, materials, compartments or airline approval.",
        'pet': "PRODUCT CATEGORY DIRECTION: Treat this as a pet accessory. Use calm, responsible handling and natural animal behavior only when relevant; do not invent safety, health, durability or training claims.",
        'automotive': "PRODUCT CATEGORY DIRECTION: Treat this as a car accessory. Keep any vehicle stationary unless the scene explicitly requires safe movement; do not show device use while driving or invent compatibility, power or safety claims.",
        'garden': "PRODUCT CATEGORY DIRECTION: Treat this as gardening or plant-care gear. Use believable garden physics and natural light; do not invent plant growth, material, weatherproofing or performance claims.",
        'kitchen': "PRODUCT CATEGORY DIRECTION: Treat this as kitchenware or a kitchen appliance. Keep food handling and appliance actions physically plausible; do not invent materials, safety ratings, temperature performance or functions.",
        'furniture': "PRODUCT CATEGORY DIRECTION: Treat this as furniture or home decor. Preserve exact proportions, joints and visible construction; do not invent materials, assembly parts, storage or load capacity.",
        'baby': "PRODUCT CATEGORY DIRECTION: Treat this as a baby or child-care product. Keep scenes calm and responsible, do not place a child in a risky situation, and do not invent safety certification, age suitability or health claims.",
        'crafts': "PRODUCT CATEGORY DIRECTION: Treat this as an art, craft or hobby product. Show only plausible tools and actions, do not invent kit contents, material composition or professional performance claims.",
        'other': "PRODUCT CATEGORY DIRECTION: Follow the product category inferred from the product name and choose a suitable presentation without guessing features.",
    }
    category_direction = product_type_directions.get(product_type, product_type_directions['other'])
    identity = (
        "PRODUCT IDENTITY RULE: The user will upload the original product photo(s) to the target AI video generator as the MASTER visual reference. "
        "Treat those photo(s), not assumptions from the product name, as the source of truth for the visible product identity. "
        "Preserve visible shape, color, print, packaging, proportions and readable branding. Do not invent unseen angles, brand marks, "
        "model numbers, materials, technical specifications, included accessories, product claims, compartments or hidden features. "
        "Use the product name and category only as supporting context; if a detail is not visible, keep it neutral rather than guessing."
    )
    art = (
        f"ART DIRECTION: Premium commercial product cinematography. Environment: {scene}. "
        "Clean, intentional negative space; product is the unmistakable hero. Soft large-key illumination, "
        "controlled fill, realistic contact shadow and restrained edge highlights. Use neutral, plausible "
        "surface rendering without claiming unprovided materials. Avoid excessive bloom or artificial plastic shine. "
        "Use elegant pacing, physically plausible movement and stable framing."
    )
    negative = (
        "STRICT EXCLUSIONS: Keep the product presentation plausible and visually consistent with the supplied product name. "
        "No dramatic spinning, flying product, aggressive morph transitions or abrupt scene changes. "
        "No invented features, extra accessories, duplicated products, fabricated logos or labels, random props that imply included items, "
        "floating geometry, distorted edges, flicker, jitter, abrupt exposure shifts, plastic-looking surfaces or unnatural hands. "
        "Do not add subtitles, UI, watermarks or promotional wording not explicitly requested. "
        "Do not invent unseen angles or claim features that are not visible in the reference image(s)."
    )
    if mode == "storyboard":
        style_key, style_name, style_template = resolve(style)
        doodle = style_key == "white_doodle"
        hook = product_hook(product)

        # Keep single 10-second prompts concise enough for one Telegram message.
        # Retain the selected style, reference safety, timed beats and user concept.
        if duration == 10:
            if part == 2:
                beat_plan = ("SECOND CLIP 10s: 0–2s continue from the exact full-product frame held at the end of Part 1; "
                             "2–4s resume the same movement; 4–6s show another visible detail; 6–8s continue in the same setting; "
                             "8–10s stable full-product hero finish. Do NOT repeat the opening hook. ")
            elif part == 1:
                beat_plan = ("FIRST CLIP 10s: 0–2s establish the product; 2–4s reveal it fully; 4–6s highlight one visible detail; "
                             "6–8s continue one simple action; 8–10s HOLD the final frame for Part 2. No fade. ")
            else:
                beat_plan = ("TIMING: 0–2s clean reveal; 2–4s show the full product; 4–6s highlight one reference-visible detail; "
                             "6–8s one subtle product-appropriate action; 8–10s stable full-product hero frame. "
                             + ("Do not perform the main surrounding contour yet. " if doodle else ""))
            if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
                beat_plan = "FOLLOW THESE SELECTED STORYBOARD BEATS IN ORDER: " + " | ".join(
                    str(item.get("shot", "")) + ": " + str(item.get("direction", ""))
                    for item in storyboard_override
                ) + ". "
            hook_rule = (
                "OPENING TEXT: Show only this neutral product/category hook, exactly: '" + hook + "'. "
                if hook and not storyboard_override else
                ("NO ON-SCREEN HOOK TEXT. Never guess a category, benefit, price, popularity or product name. "
                 if not hook and not storyboard_override else
                 "ON-SCREEN TEXT: No text, captions, extra logos or watermark unless explicitly requested. ")
            )
            doodle_rule = (
                "GRAPHICS: Thin white hand-drawn marks may emphasize visible product edges only; never cover the product. "
                if doodle else ""
            )
            concept_rule = ("CREATIVE IDEA: " + concept.strip() + ". " if concept and concept.strip() else "")
            return (
                "KLIPPO — VIDEO PROMPT | 10 SECONDS" + (" | PART " + str(part) if part else "") + "\n"
                "Vertical 9:16, one realistic product ad, exactly 10 seconds.\n"
                "PRODUCT: " + product + "\n"
                + category_direction + "\n"
                + "STYLE: " + style_name + " — " + style_template + "\n"
                + "SETTING: " + scene + ". CAMERA: " + camera + "\n"
                + hook_rule + beat_plan + concept_rule + doodle_rule
                + "REFERENCE LOCK: Use the uploaded photo as the source of truth. Preserve visible shape, colour, print, packaging, proportions and branding. "
                "Do not invent features, materials, accessories, unseen angles, claims or text. "
                "Use natural light and shadows, believable physics, stable product geometry and smooth restrained motion; avoid morphing, flicker, CGI/plastic skin and abrupt scene changes."
            )

        evidence_rules = (
            "REFERENCE IMAGE RULE: The video generator will receive the user's original product photo(s) as visual evidence. "
            "Inspect only details genuinely visible in those reference photo(s), and preserve the product name and spelling supplied by the user. "
            "Use the name and optional user text as supporting context, not as permission to invent features. "
            "Do not invent unseen sides, materials, dimensions, compartments, accessories, product benefits, model numbers or specifications. "
            "If a detail is not visible or confirmed, keep it neutral and omit the claim."
        )

        hook_direction = (
            "ON-SCREEN HOOK: Display EXACTLY '" + hook + "' at the top safe area in the opening 0-2s. "
            "This is a neutral category/name hook only, not a product benefit claim. "
            "Keep the product unobstructed and do not add any other unverified promotional copy. "
        ) if hook else (
            "NO ON-SCREEN HOOK TEXT: Begin with a clean product reveal and no headline. "
            "Never guess a category, benefit, price, popularity or product name."
        )
        if storyboard_override:
            hook_direction = (
                "NO ON-SCREEN TEXT: Do not add a hook, headline, captions, labels, logos or watermark. "
                "Follow the selected product-specific storyboard."
            )
        if doodle:
            if part > 1:
                rules = (
                    "SECOND CLIP 10s, five 2-second panels: 0-2s resume from the exact final full-product frame held at the end of Part 1; "
                    "2-4s begin drawing a thin white dashed contour just OUTSIDE the actual product silhouette; "
                    "following only visible product edges; 4-6s complete and hold the contour. "
                    "6-8s add one small white dotted arrow or sparkle beside a genuinely visible detail; "
                    "8-10s clean full-product hero packshot, gracefully fade the doodle. Do NOT repeat the opening hook. "
                )
            else:
                rules = (
                    "FIRST CLIP 10s, five 2-second panels: 0-2s close-up with a verified product-name/category hook if available; "
                    "2-4s full product reveal; 4-6s one genuinely visible detail; 6-8s restrained white doodle emphasis; "
                    "8-10s settle into a steady full-product composition and HOLD the final frame for a seamless Part 2 handoff. "
                    "Do not perform the main surrounding contour yet. "
                )
            rules += (
                "Warm authentic UGC product-ad look, thin white handwritten 2D graphics tracked to the product. "
                "No phone bezel, no invented product claims, no branding obstruction. Only verified hook (if available) and verified "
                "short feature labels may appear; reserve space for editing overlays if text rendering is unreliable. "
                "Prioritize the visible surrounding product contour over camera movement."
            )
        elif part > 1:
            rules = (
                "SECOND CLIP 10s, five 2-second panels: 0-2s continue the exact full-product frame held at the end of Part 1; "
                "2-4s emphasize a second genuinely visible detail without inventing an angle; 4-6s continue the same concept; "
                "6-8s elegant style-specific visual emphasis; 8-10s full-product hero closing and fade. Do NOT repeat the opening hook."
            )
        else:
            rules = (
                "FIRST CLIP 10s, five 2-second panels: 0-2s verified product-name/category hook if available; "
                "2-4s full-product reveal; 4-6s one genuinely visible detail; 6-8s continue the product story; "
                "8-10s settle into a stable full-product frame and HOLD for a seamless Part 2 handoff. No closing fade in Part 1."
            )
        if part == 0 and duration > 10:
            rules = (
                "SINGLE-PROMPT FULL-LENGTH VIDEO: Create one continuous " + str(duration) + "-second product commercial, not separate clips. "
                "Distribute these five connected beats across the entire duration: opening product recognition; full-product reveal; "
                "one genuinely visible detail; a restrained style-specific action; and a stable full-product hero finish. "
                "Keep the same set, lighting, product scale and identity throughout. "
                + ("Use thin white doodle emphasis only around visible product edges, without obscuring the product. " if doodle else "")
                + "Do not repeat the opening or introduce unsupported features, props, text or unseen angles."
            )
        curated_direction = ""
        if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
            curated_shots = list(storyboard_override)
            if part == 2:
                curated_shots = [
                    {
                        "time": "0–2s",
                        "shot": "CONTINUITY BRIDGE",
                        "direction": (
                            "Resume from the exact final product framing of Part 1 with the same set, lighting, "
                            "orientation and scale. Do not repeat the opening hook or restart the reveal."
                        ),
                    },
                    {
                        **curated_shots[1],
                        "direction": (
                            "CONTINUATION ACTION — do not repeat the main gesture from Part 1. Continue the same concept with "
                            "a complementary, physically plausible follow-through while keeping the same product, set, light and scale. "
                            + str(curated_shots[1].get("direction", ""))
                        ),
                    },
                    curated_shots[2],
                    curated_shots[3],
                ]
            curated_direction = (
                "DIRECTOR'S CURATED PREMIUM STORYBOARD: Use this selected GitHub library storyboard as the primary shot plan. "
                "Expand the four selected creative beats into five connected beats distributed across the full requested duration; add a reference-safe opening or closing beat where needed. Preserve the same product identity, packaging, color, scale and coherent set. "
                "NO ON-SCREEN TEXT, captions, added logos, watermarks, dialogue or voice-over unless explicitly requested.\n\n"
                + "\n\n".join(
                    str(item.get("time", "")) + " | " + str(item.get("shot", "")) + "\n"
                    + "VISUAL AND CAMERA BRIEF: " + str(item.get("direction", ""))
                    for item in curated_shots
                )
                + "\n\nPREMIUM CINEMATOGRAPHY: Controlled key and fill light, elegant camera easing, realistic depth of field, "
                "natural contact shadows, clean transitions and restrained highlights. Keep product geometry and visible details "
                "consistent throughout. Finish on a stable, clean hero frame."
            )
        # Standardize every Telegram storyboard prompt, including curated library styles,
        # on five equal timed scenes within one video.
        if part == 0 and duration in (10, 20):
            scene_length = duration / 5
            generic_scenes = [
                ("OPENING / PRODUCT REVEAL", "Establish the exact product clearly in a coherent setting; no on-screen text."),
                ("FULL PRODUCT VIEW", "Show the complete product, preserving shape, colour, print, proportions, packaging and visible branding."),
                ("VISIBLE DETAIL", "Move gently toward a genuinely visible detail; do not invent unseen surfaces, textures or features."),
                ("NATURAL PRODUCT ACTION", "Show one simple, physically plausible product-appropriate action or restrained camera move."),
                ("FINAL HERO HOLD", "Return to a clean, stable full-product composition. No invented slogan, price, claim or watermark."),
            ]
            if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
                curated_items = list(storyboard_override)
                generic_scenes = [
                    ("OPENING / PRODUCT REVEAL", "Establish the exact product clearly in a coherent setting; no on-screen text."),
                    (str(curated_items[0].get("shot", "CREATIVE BEAT 1")), str(curated_items[0].get("direction", ""))),
                    (str(curated_items[1].get("shot", "CREATIVE BEAT 2")), str(curated_items[1].get("direction", ""))),
                    (str(curated_items[2].get("shot", "CREATIVE BEAT 3")), str(curated_items[2].get("direction", ""))),
                    ("CREATIVE FINISH / HERO HOLD", str(curated_items[3].get("direction", "")) + " Finish on a stable, full-product hero frame."),
                ]
            blocks = []
            for index, (shot_name, shot_direction) in enumerate(generic_scenes):
                start = index * scene_length
                end = start + scene_length
                blocks.append(f"SCENE {index + 1} — {start:.1f}–{end:.1f}s | {shot_name}: {shot_direction}")
            storyboard_text = (
                "DIRECTOR'S WRITTEN STORYBOARD: Generate ONE continuous vertical product video with exactly five equal scenes. "
                f"Each scene lasts exactly {scene_length:g} seconds. These are timed scenes inside one video, not separate prompts or a storyboard image. "
                "No unrequested text, captions, added logos, dialogue, voice-over, claims or watermarks. "
                "Preserve exact product identity, packaging, colour, scale and coherent lighting.\\n\\n"
                + "\\n\\n".join(blocks)
                + "\\n\\nKeep transitions natural, camera movement restrained and product geometry stable throughout."
            )
            if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
                curated_direction = storyboard_text
            else:
                rules = storyboard_text
        return (
            "PROMPT VIDEO — " + str(duration) + " SAAT\n"
            "KLIPPO | UNIVERSAL PRODUCT VIDEO PROMPT | " + style_name + (" | BAHAGIAN " + str(part) if part else "") + "\n"
            "OUTPUT: One cohesive vertical 9:16 product advertisement, target resolution 1080x1920, EXACT DURATION: " + str(duration) + " seconds.\n\n"
            "PRODUCT NAME: " + product + "\n" + category_direction + "\n\n" + identity + "\n\n"
            "STYLE FROM KLIPPO CATALOG: " + style_template + "\n\n"
            "SETTING: " + scene + "\n"
            "CAMERA: " + camera + " Keep framing plausible for the named product; avoid unsupported angles or features.\n\n"
            + evidence_rules + "\n\n" + (
                curated_direction if curated_direction else
                (hook_direction if part != 2 else "NO REPEATED OPENING HOOK in Part 2.") + "\n\n" + rules
            ) + "\n\n"
            + (("OPTIONAL CREATIVE CONCEPT: " + concept + ". Use it only to guide a suitable, physically plausible action or story beat; "
                 "do not treat it as proof of product features, benefits, included accessories or unseen details. "
                 "If the idea requires an unprovided feature, ignore that part.\n\n") if concept else "")
            +  "CONTINUITY: Keep a consistent, plausible presentation of the named product throughout the video. "
            "Use soft physically believable lighting and stable background. "
            "Do not morph the object, invent accessories or cover its visible branding. "
            "For white doodle, the graphic overlays are explicitly REQUIRED and are not captions or UI. "
            "If the video generator cannot render precise overlays, generate clean product footage and add doodles in post-production."
        )
    if mode == "storyboard":
        shots = [
            ("01 | HOOK | 0–2s", "Open with a compelling but reference-safe close view. Use a subtle camera move and light reveal; do not invent a product feature."),
            ("02 | REVEAL | 2–4s", "Reveal the complete product in a balanced frame. Keep scale, proportions and orientation faithful to the reference."),
            ("03 | CONTEXT | 4–6s", "Place the same product in a believable setting suited to its category. Do not add props that imply included accessories or unsupported functions."),
            ("04 | DETAIL | 6–8s", "Emphasize one genuinely visible detail using a controlled close-up. Do not reveal unseen sides or fabricate material details."),
            ("05 | HERO CLOSING | 8–10s", "Return to a clean full-product hero frame. Ease into a stable hold and a subtle fade; no invented slogan, price or claim.")
        ]
        direction = ("DIRECTOR'S FIVE-PANEL STORYBOARD: Deliver one cohesive commercial with exactly five panels, each exactly 2 seconds. "
                      "Treat these as connected editing beats, not five different product designs. Keep the same product identity, "
                      "spatial orientation, visual palette and believable light direction in every panel.\n\n"
                      + "\n\n".join(title + "\nVISUAL AND CAMERA BRIEF: " + detail for title, detail in shots)
                      + "\n\nEDITING AND CONTINUITY: Use clean match cuts or gentle transitions. Every panel must advance the story from curiosity "
                      "to product recognition, a visible detail and a memorable closing hero frame. Avoid flashy templates, random zooms and inconsistent set geometry.")
    else:
        direction = (
            "DIRECTOR'S SINGLE-TAKE BRIEF: Create one sophisticated uninterrupted " + str(duration) + "-second commercial, "
            "not a slideshow, montage or set of disconnected AI shots. Keep the product almost stationary while the camera or light moves gently; one primary camera move only. The visual story progresses from "
            "anticipation to discovery and finally a confident product hero moment.\n\n"
            "0.0–2.0s | OPENING: Begin with a deliberately composed medium-wide shot. Establish the selected "
            "environment with natural perspective, restrained highlights and believable grounding. Introduce "
            "the product using a delicate light reveal rather than sudden object appearance. Keep its visible "
            "branding and outline stable from the first frame.\n\n"
            "2.0–5.0s | DEVELOPMENT: Start the requested camera move with gradual acceleration: " + camera +
            " Build depth through the background and lighting rather than bending or reconstructing the object. Do not rotate the product or reveal an unseen side. "
            "Hold a clean focal plane on the product. Show only surfaces genuinely supported by the reference.\n\n"
            "5.0–7.5s | VISUAL EMPHASIS: Refine the composition around a visible material, finish or design detail. "
            "Use subtle controlled light falloff and accurate reflections. Preserve the exact packaging and "
            "typography, without enhancing unreadable text into invented words. Keep movement continuous and natural.\n\n"
            "7.5–10.0s | HERO FINISH: Ease the camera into a balanced full-product composition. Let the product "
            "remain clearly legible, with polished edge separation and a stable contact shadow. Finish on a "
            "brief confident hold with an understated lighting accent. No unrequested caption, CTA or watermark; follow the ON-SCREEN TEXT rule exactly.\n\n"
            "CINEMATOGRAPHY: Premium commercial lens language, elegant motion curves, coherent depth of field, "
            "physically plausible parallax and natural material response. Maintain one consistent studio space "
            "and color grade throughout; avoid frantic motion, jump cuts, fake rotations or excessive effects."
        )
    if duration == 20:
        direction = (
            "DIRECTOR'S SINGLE-TAKE 20-SECOND BRIEF: 0-4s establish the named product in its setting; "
            "4-8s restrained camera push or lateral movement with realistic parallax; "
            "8-12s emphasize a genuinely visible detail using subtle focus and light; "
            "12-16s ease back to a complete recognizable product view with the same identity and background; "
            "16-20s elegant hero hold and gentle fade. Keep continuity, avoid new unseen angles, "
            "avoid added text or invented features. This is one coherent commercial, not a slideshow."
        )
    if part == 1:
        direction = ("FIRST CLIP 10s, five 2-second panels: 0-2s establish the product; 2-4s reveal the complete product; "
                     "4-6s focus on one genuinely visible detail; 6-8s continue a complementary action; "
                     "8-10s return to a stable full-product frame and hold without fade to connect directly into Part 2.")
    elif part == 2:
        direction = ("SECOND CLIP 10s, five 2-second panels: start with the EXACT held full-product final frame from Part 1, "
                     "matching crop, product position, orientation, setting, lighting and color. "
                     "0-2s resume the same movement; 2-4s continue the action; 4-6s highlight another visible detail; "
                     "6-8s maintain coherent context; 8-10s full-product hero finish with graceful fade. No new product, scene or angle.")
    product_words = (product or "").lower()
    fashion_terms = ("kurung", "baju", "tudung", "hijab", "dress", "clothing", "apparel",
                     "fashion", "outfit", "blouse", "skirt", "trousers", "pants", "garment",
                     "woman wearing", "model wearing", "pakaian", "kebaya", "jubah", "abaya")
    is_fashion = any(term in product_words for term in fashion_terms)
    if is_fashion and mode != "storyboard" and part == 0 and duration != 20:
        direction = (
            "DIRECTOR'S NATURAL FASHION TRY-ON BRIEF: Create one continuous, believable 10-second vertical fashion video, "
            "like authentic iPhone footage filmed at home before going out. If a person is included in the scene, keep their appearance and outfit consistent; "
            "if no person is needed for the scene, do not add one. For a mirror-selfie style, use a believable mirror and phone composition. "
            "0–2s | ESTABLISH: Use a simple, consistent outfit and believable room setting; use soft natural morning light and realistic skin and fabric texture. "
            "2–5s | NATURAL ACTION: The person makes one small, relaxed movement appropriate to the reference, such as gently lowering the phone a little to reveal more of the outfit or making a slight body turn. "
            "Keep actions simple and plausible. 5–8s | OUTFIT DETAIL: Let the camera or person move subtly to show the stated garment style; never fabricate hidden garment details. "
            "8–10s | FINISH: Return to a relaxed, natural pose and hold briefly. Keep movement subtle, human and physically plausible; no dancing, exaggerated posing or scene changes. "
            "FASHION PRODUCT LOCK: The exact garment must remain unchanged frame to frame—same color, print, pattern placement, neckline, sleeves, cut, fit, fabric, accessories and proportions. "
            "Keep the chosen hijab style and handbag presentation consistent. Never redesign, recolor, reshape, add or remove stated outfit details. "
            "Use one consistent home setting, authentic phone-camera perspective, soft daylight and crisp fabric detail. No collage, split screen, poster layout, outfit change, plastic skin or CGI."
        )
    return (
        "KLIPPO | PROFESSIONAL IMAGE-TO-VIDEO PRODUCTION PROMPT" + (" | BAHAGIAN " + str(part) if part else "") + "\n"
        "OUTPUT: " + str(duration) + " seconds; portrait 9:16; high-quality realistic product commercial; "
        "one coherent deliverable. ON-SCREEN TEXT: Follow the KLIPPO GUIDED CREATIVE SETTINGS language choice. If the language is none, show no text. Otherwise, use at most the exact product name supplied by the user unless exact wording is provided; do not invent marketing claims or promotional copy. Preserve spelling, keep text brief and legible, and place it away from the product.\n\n"
        "PRODUCT: " + product + "\n" + category_direction + "\n\n" + identity + "\n\n" + art + "\n\n"
        + direction + "\n\n" + negative + "\n\n"
        "FINAL QUALITY CHECK: Consistent identity in every frame, natural physics, clean edges, "
        "stable illumination, smooth temporal coherence and polished affiliate-ad aesthetics. "
        "If the product name does not support a requested feature or viewpoint, use a safe crop or modest "
        "2D camera movement instead of hallucinating the product."
    )
