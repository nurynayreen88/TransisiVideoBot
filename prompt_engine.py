from prompt_catalog import resolve, product_hook
"""Detailed, reference-safe AI video prompt templates for KLIPPO."""

CAMERAS = {
    "orbit": "A restrained camera arc of at most 30 degrees with subtle parallax. Never reveal or fabricate an unseen side.",
    "push": "A smooth slow dolly-in from a balanced medium product shot to a crisp detail, with no digital warping.",
    "side": "A measured left-to-right lateral camera slide with gentle depth separation and stable product proportions.",
    "static": "A locked premium studio composition with delicate lighting movement and a subtle focus transition.",
}

AUTO_STYLE_BY_PRODUCT_TYPE = {
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
    'other': 'cinematic',
}


def _resolve_auto_style(style, product_type):
    """Choose a stable, category-appropriate catalog style without an AI call."""
    if style != 'auto':
        return style
    return AUTO_STYLE_BY_PRODUCT_TYPE.get(product_type, 'cinematic')


def build_prompt(mode, product, scene, motion, style='auto', duration=10, concept='', product_type='other', storyboard_override=None):
    style = _resolve_auto_style(style, product_type) if mode == 'storyboard' else style
    if duration == 20:
        # Resolve the category-appropriate style once so both clips remain consistent.
        chosen_style = style
        first = _build_single_prompt(mode, product, scene, motion, chosen_style, part=1, concept=concept, product_type=product_type, storyboard_override=storyboard_override)
        second = _build_single_prompt(mode, product, scene, motion, chosen_style, part=2, concept=concept, product_type=product_type, storyboard_override=storyboard_override)
        return first + "\n\n=== KLIPPO PART 2 ===\n\n" + second
    return _build_single_prompt(mode, product, scene, motion, style, part=0, concept=concept, product_type=product_type, storyboard_override=storyboard_override)


def _build_single_prompt(mode, product, scene, motion, style='auto', part=0, concept='', product_type='other', storyboard_override=None):
    duration = 10
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
        "Use the product name and category only as supporting context; if a detail is not visible, keep it neutral rather than guessing. REAL-WORLD SCALE IS MANDATORY: preserve ordinary physical dimensions relative to fingers, hands, wrists, people, furniture and surroundings. A ring must remain finger-sized and must never become table-sized; achieve macro close-ups with camera framing, never by enlarging the physical object. Watches must fit wrists, phones must fit hands, and scale must stay stable in every shot. If exact dimensions are unknown, use realistic category-appropriate proportions."
    )
    art = (
        f"ART DIRECTION: Premium commercial product cinematography. Environment: {scene}. "
        "Clean, intentional negative space; product is the unmistakable hero. Soft large-key illumination, "
        "controlled fill, realistic contact shadow and restrained edge highlights. Use neutral, plausible "
        "surface rendering without claiming unprovided materials. Avoid excessive bloom or artificial plastic shine. "
        "Use elegant pacing, physically plausible movement and stable framing. "
        "PHOTOREALISM FIRST: Make the result resemble genuine live-action footage from a real camera, not CGI, 3D render, illustration or synthetic AI advertising. Use believable lens perspective, natural texture, imperfect but controlled real-world light, realistic contact shadows and restrained color grading. Avoid waxy surfaces, over-smoothed skin, excessive sharpness, fake bokeh, HDR halos, excessive bloom, impossible reflections, sterile showroom CGI and unnaturally perfect symmetry. "
        "If a human model is appropriate, preserve a consistent natural face, skin texture, body proportions, hair and clothing; use relaxed posture, subtle expressions, correct anatomy and physically accurate hand-to-product contact. If no model is needed, do not add a person or hands just to decorate the scene. Keep the product physically grounded, correctly scaled and unchanged at true real-world scale. Macro framing may magnify the view but must never change the object's physical dimensions; keep rings finger-sized, watches wrist-sized and handheld products proportionate to the hand."
    )
    negative = (
        "STRICT EXCLUSIONS: Keep the product presentation plausible and visually consistent with the supplied product name. "
        "No dramatic spinning, flying product, aggressive morph transitions or abrupt scene changes. "
        "No invented features, extra accessories, duplicated products, fabricated logos or labels, random props that imply included items, "
        "floating geometry, distorted edges, flicker, jitter, abrupt exposure shifts, plastic-looking surfaces or unnatural hands. "
        "Do not add subtitles, UI, watermarks or promotional wording not explicitly requested. "
        "Do not invent unseen angles or claim features that are not visible in the reference image(s). "
        "Avoid obvious AI artifacts: uncanny or inconsistent faces, waxy/plastic skin, extra or fused fingers, malformed hands, duplicated limbs, changing garment patterns, warped product geometry, floating objects, inconsistent shadows, impossible reflections, texture shimmer, flicker, frame-to-frame identity drift, oversaturated synthetic colors and fake cinematic effects. "
        "Do not force a human model into a product-only scene; do not force a floating product or impossible camera orbit into a model-led scene. Prefer one simple, physically credible action over multiple complicated actions."
    )
    if mode == "storyboard":
        style_key, style_name, style_template = resolve(style)
        doodle = style_key == "white_doodle"
        hook = product_hook(product)
        evidence_rules = (
            "REFERENCE IMAGE RULE: The video generator will receive the user's original product photo(s) as visual evidence. "
            "Inspect only details genuinely visible in those reference photo(s), and preserve the product name and spelling supplied by the user. "
            "Use the name and optional user text as supporting context, not as permission to invent features. "
            "Do not invent unseen sides, materials, dimensions, compartments, accessories, product benefits, model numbers or specifications. "
            "If a detail is not visible or confirmed, keep it neutral and omit the claim."
        )

        hook_direction = (
            "VISUAL HOOK: Create immediate curiosity through a product-specific camera reveal or plausible action in the opening 0–2 seconds. NO ON-SCREEN TEXT: never display the hook as written text. If voiceover is enabled in the guided settings, the hook may be spoken only. Never invent a product benefit claim. "
        ) if hook else (
            "NO ON-SCREEN TEXT: Begin with a clean product reveal and use composition or action as the visual hook. "
            "Never guess a category, benefit, price, popularity or product name."
        )
        if storyboard_override:
            hook_direction = (
                "NO ON-SCREEN TEXT: Do not add a hook headline, captions, written labels, added logos, watermarks or UI. Use the selected product-specific storyboard; if voiceover is enabled, keep the hook in spoken audio only."
            )
        if doodle:
            if part == 2:
                rules = (
                    "SECOND CLIP 10s, five 2-second panels: 0-2s resume from the exact final full-product framing of Part 1; "
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
                "No phone bezel, no invented product claims, and no branding obstruction. "
                "Use only flat visual lines, simple arrows and small sparkles; no letters, words, feature labels or captions. "
                "Keep graphics clear of the product and prioritize tracing its actual visible contour over camera movement."
            )
        elif part == 2:
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
                "Expand the four selected creative beats into exactly five connected panels of 2 seconds each; distribute the selected beats across the panels and add a reference-safe opening or closing panel where needed. Preserve the same product identity, packaging, color, scale and coherent set. "
                "NO ON-SCREEN TEXT, captions, added logos, watermarks or UI. If the guided settings explicitly enable voiceover, follow their language, accent, duration and audio-mix instructions; otherwise use no dialogue.\n\n"
                + "\n\n".join(
                    str(item.get("time", "")) + " | " + str(item.get("shot", "")) + "\n"
                    + "VISUAL AND CAMERA BRIEF: " + str(item.get("direction", ""))
                    for item in curated_shots
                )
                + "\n\nPREMIUM CINEMATOGRAPHY: Controlled key and fill light, elegant camera easing, realistic depth of field, "
                "natural contact shadows, clean transitions and restrained highlights. Keep product geometry and visible details "
                "consistent throughout. Finish on a stable, clean hero frame."
            )
        return (
            "PROMPT VIDEO — 10 SAAT\n"
            "KLIPPO | UNIVERSAL PRODUCT VIDEO PROMPT | " + style_name + (" | BAHAGIAN " + str(part) + "/2" if part else "") + "\n"
            "OUTPUT: One cohesive vertical 9:16 product advertisement, EXACT DURATION: " + str(duration) + " seconds.\n\n"
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
            "Use one consistent home setting, authentic phone-camera perspective, soft daylight and crisp fabric detail. Skin must retain pores and natural texture; facial features, fingers, joints, hair and fabric folds must remain anatomically and physically believable. Use relaxed breathing, subtle weight shifts and natural timing rather than a frozen pose or robotic motion. Keep the same real-looking person and garment in every frame; no face drift, beauty-filter skin, uncanny eyes, extra fingers, rubbery limbs, fabric shimmer, pattern drift, over-smoothed skin, CGI sheen or artificial slow motion. No collage, split screen, poster layout, outfit change, plastic skin or CGI."
        )
    if duration == 10 and part == 0:
        # Compact 10-second prompt: keep the creative intent in one Telegram message.
        selected_beats = ""
        if storyboard_override and isinstance(storyboard_override, (list, tuple)):
            beat_lines = []
            for beat in storyboard_override[:4]:
                if isinstance(beat, dict):
                    beat_lines.append(str(beat.get("time", "")) + " " + str(beat.get("shot", "")) + ": " + str(beat.get("direction", "")))
                else:
                    beat_lines.append(str(beat))
            if beat_lines:
                selected_beats = "SELECTED SHOT IDEAS: " + " ".join(beat_lines) + "\n"
        compact = (
            "KLIPPO | REALISTIC 10-SECOND PRODUCT VIDEO\n"
            "FORMAT: vertical 9:16, one coherent live-action-style commercial, 10 seconds.\n"
            "PRODUCT: " + product + "\n" + category_direction + "\n"
            "REFERENCE LOCK: Use uploaded photo(s) as truth. Preserve visible shape, colour, print, packaging, logo and proportions. Never invent unseen features, materials, accessories or claims. REAL-WORLD SCALE IS MANDATORY: rings remain finger-sized, watches fit wrists, phones fit hands, and furniture/appliances keep believable proportions relative to people and rooms. Use macro framing rather than physically enlarging small objects.\n"
            "SCENE: " + str(scene) + ". " + (("CONCEPT: " + str(concept) + ". ") if concept else "") + "\n"
            + selected_beats
            + "SHOT FLOW: 0–2s natural opening/reveal; 2–5s one gentle camera move (" + str(camera) + "); "
            "5–8s highlight one visible detail; 8–10s settle into a clear full-product hero frame and hold. "
            "Use one simple, physically possible action; keep the product grounded and stable. No montage, sudden scene change or impossible orbit.\n"
            "PHOTOREALISM: Must resemble real camera footage, not CGI, 3D render or AI art. Natural material and skin texture; realistic hands/anatomy if a model is included; consistent face, body, clothing and product. Use believable lens perspective, soft real-world light, contact shadows and plausible reflections. Do not add a person if none is needed.\n"
            "AVOID: waxy skin, uncanny faces, extra/fused fingers, warped product, changing patterns, floating objects, fake reflections, plastic shine, excessive bokeh/HDR, flicker, jitter, identity drift, invented props, captions, added logos or watermarks.\n"
            "FINAL CHECK: believable physics, consistent product identity, natural motion, realistic physical scale, no on-screen text or added branding, and understated commercial polish."
        )
        return compact
    return (
        "KLIPPO | PROFESSIONAL IMAGE-TO-VIDEO PRODUCTION PROMPT" + (" | BAHAGIAN " + str(part) + "/2" if part else "") + "\n"
        "OUTPUT: " + str(duration) + " seconds; portrait 9:16; high-quality realistic product commercial; "
        "one coherent deliverable. NO ON-SCREEN TEXT: Do not generate captions, headlines, labels, subtitles, UI overlays, added logos or watermarks. Use a visual hook through composition and action only; any selected hook or CTA must be spoken audio, never written on screen. Preserve only branding physically present on the actual reference product.\n\n"
        "PRODUCT: " + product + "\n" + category_direction + "\n\n" + identity + "\n\n" + art + "\n\n"
        + direction + "\n\n" + negative + "\n\n"
        "FINAL REALISM CHECK: The result should pass as authentic live-action commercial footage at first glance, not as an AI-generated image or animation. Consistent product identity in every frame, realistic skin and hand anatomy if a person appears, natural fabric or material texture, grounded contact shadows, plausible reflections, stable exposure, real-camera perspective and physically possible movement. Avoid the polished-but-fake CGI look, artificial skin smoothing, impossible object motion, warped geometry, flicker and temporal identity drift. "
        "FINAL QUALITY CHECK: Consistent identity in every frame, natural physics, clean edges, "
        "stable illumination, smooth temporal coherence and polished affiliate-ad aesthetics. "
        "If the product name does not support a requested feature or viewpoint, use a safe crop or modest "
        "2D camera movement instead of hallucinating the product."
    )
