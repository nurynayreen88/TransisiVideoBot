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
    'toys': 'playful_viral',
    'bag': 'handbag_showcase',
    'wallet': 'wallet_luxury_macro',
    'hijab': 'fashion_editorial',
    'shoes': 'studio_360_safe',
    'beauty': 'beauty_macro',
    'food': 'food_appetite',
    'stationery': 'flatlay',
    'sports': 'lifestyle',
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


def _model_age_direction(product, product_type='other'):
    """Conservatively match any human fashion model to explicit product age cues."""
    name = (product or '').casefold()
    if product_type not in ('fashion', 'hijab', 'shoes', 'bag', 'accessory', 'other'):
        return ""
    baby_terms = ('babyshop', 'baby ', 'newborn', 'new born', 'bayi', 'infant', 'baby clothes', 'baju baby',
                  'baju bayi', 'romper bayi', 'toddler', '0-3 bulan', '3-6 bulan',
                  '6-12 bulan', '12-18 bulan', '18-24 bulan')
    child_terms = ('kanak-kanak', 'kanak kanak', 'budak', 'kids', 'kid ', 'children',
                   'child ', 'boy ', 'girl ', 'baju sekolah rendah', 'uniform sekolah rendah',
                   'toddler', 'saiz kanak', 'size kids', 'kidswear', 'pakaian kanak')
    adult_terms = ('dewasa', 'adult', 'women', 'woman', 'ladies', 'men ', 'mens',
                   'lelaki dewasa', 'wanita dewasa', 'plus size', 'saiz dewasa',
                   'baju kurung', 'kebaya', 'jubah', 'abaya', 'blazer', 'office wear')
    if any(term in name for term in baby_terms):
        return ("AGE-APPROPRIATE MODEL LOCK: This product is explicitly for babies/infants. Do not put it on an adult or older child. "
                "Use a safe, age-appropriate baby product presentation only when appropriate; otherwise show the garment laid flat or on a suitable mannequin. "
                "Never show unsafe handling, unsupported fit claims or a risky pose.")
    if any(term in name for term in child_terms):
        return ("AGE-APPROPRIATE MODEL LOCK: This product is explicitly for children. Use a child model whose apparent age fits the stated size/category; "
                "never substitute an adult model. Keep posing modest, natural and age-appropriate, with safe supervision implied where relevant.")
    if any(term in name for term in adult_terms):
        return ("AGE-APPROPRIATE MODEL LOCK: This product is explicitly adult clothing/fashion. Use an unmistakably adult model; "
                "do not use a child or teen-looking model. Keep styling and pose appropriate to the garment.")
    if any(term in name for term in ('baju', 'pakaian', 'dress', 'clothing', 'apparel', 'uniform',
                                     'blouse', 'skirt', 'seluar', 'pants', 'shirt', 'tudung',
                                     'hijab', 'kasut', 'shoes', 'sandal', 'sneakers', 'fashion',
                                     'garment', 'outfit', 'jacket', 'hoodie', 'cardigan')):
        return ("AGE-APPROPRIATENESS CHECK: The product name does not reliably establish the intended age. "
                "Do not guess or mix age groups. Prefer a product-only flat lay/mannequin without a human model unless age suitability is clear from the reference, sizing or product details. "
                "If the available details clearly establish the age group, use only a model from that matching group and keep appearance consistent across all shots.")
    return ""


# Product-category markers remove only curated beats that explicitly reference unrelated categories.
_CATEGORY_MARKERS = {
    "footwear": ("footwear", "shoes", "shoe", "sneaker", "sandal", "boot", "outsole", "laces", "lace touch", "heel"),
    "clothing": ("garment", "clothing", "fashion", "outfit", "sleeve", "hemline", "neckline", "blouse", "dress", "trousers", "fabric drape"),
    "bags": ("handbag", "backpack", "crossbody bag", "shoulder bag", "bag strap", "bag handle"),
    "wallet": ("wallet", "card slot", "coin pocket", "card holder"),
    "beauty": ("cosmetic", "skincare", "makeup", "lipstick", "serum", "beauty product", "apply to skin"),
    "food": ("food", "drink", "ingredient", "topping", "garnish", "edible", "pour into a glass", "appetizing"),
    "stationery": ("stationery", "notebook", "writing desk", "study desk", "pen tip", "pencil", "paper page"),
    "sports": ("fitness equipment", "sports equipment", "workout", "exercise gear", "athletic equipment"),
    "gadget": ("electronic device", "gadget", "screen interface", "charging port", "power button", "device ports"),
    "jewellery": ("jewellery", "jewelry", "ring", "necklace", "bracelet", "earring", "gemstone", "jewelled"),
    "travel": ("luggage", "suitcase", "travel gear", "packing cube", "airline cabin"),
    "pet": ("pet", "dog", "cat", "collar", "leash", "pet accessory"),
    "automotive": ("car accessory", "vehicle dashboard", "car interior", "windshield", "driving"),
    "garden": ("gardening", "garden tool", "plant care", "soil", "watering plant", "potted plant"),
    "kitchen": ("kitchenware", "cookware", "kitchen appliance", "cooking utensil", "food preparation"),
    "furniture": ("furniture", "sofa", "chair upholstery", "cabinet", "table legs", "shelving unit"),
    "baby": ("baby product", "infant", "diaper", "stroller", "crib", "child-care product"),
    "crafts": ("craft kit", "hobby supplies", "paintbrush", "glue gun", "art supplies"),
    "toys": ("toy", "toys", "playset", "building blocks", "plush toy", "doll", "action figure", "puzzle", "board game"),
}
_PRODUCT_CATEGORY_GROUP = {
    "fashion": "clothing", "hijab": "clothing", "shoes": "footwear",
    "bag": "bags", "wallet": "wallet", "beauty": "beauty", "food": "food",
    "stationery": "stationery", "sports": "sports", "gadget": "gadget",
    "accessory": "jewellery", "travel": "travel", "pet": "pet",
    "automotive": "automotive", "garden": "garden", "kitchen": "kitchen",
    "furniture": "furniture", "baby": "baby", "crafts": "crafts",
    "home": "furniture", "toys": "toys", "other": "other",
}
_CATEGORY_SAFE_SHOTS = {
    "footwear": ("PRODUCT DETAIL", "Show a close, stable view of a genuinely visible footwear detail, then return to the complete product. Preserve its real shape, sole and proportions."),
    "clothing": ("PRODUCT DETAIL", "Show a close, natural view of the selected garment's visible fabric, cut or pattern, then return to the complete garment without changing its design."),
    "bags": ("PRODUCT DETAIL", "Show a close, stable view of the actual bag shape, visible handles or straps, and finish; do not add compartments or accessories."),
    "wallet": ("PRODUCT DETAIL", "Show the actual wallet from a clear angle and reveal only visible edges, closure or interior details; do not invent slots or capacity."),
    "beauty": ("PRODUCT DETAIL", "Show the actual product packaging and a close-up of its visible texture or applicator, only where supported by the product description."),
    "food": ("PRODUCT DETAIL", "Show the actual food or drink clearly, with a realistic close-up of its visible texture and a clean final product view."),
    "stationery": ("PRODUCT DETAIL", "Show the actual stationery item in a plausible close-up and simple use; do not add other supplies or readable generated writing."),
    "sports": ("PRODUCT DETAIL", "Show the actual sports or fitness item at realistic scale, with a safe, plausible use only when its function is clear."),
    "gadget": ("PRODUCT DETAIL", "Show the actual device's visible shape and controls in a stable close-up; do not invent ports, interface content or functions."),
    "jewellery": ("PRODUCT DETAIL", "Show the actual accessory or jewellery with realistic scale and restrained reflections; do not add stones, engravings or materials."),
    "travel": ("PRODUCT DETAIL", "Show the actual travel item clearly, focusing on visible construction and a plausible handling movement without assuming capacity."),
    "pet": ("PRODUCT DETAIL", "Show the actual pet item clearly at realistic scale; include an animal only if relevant and keep handling calm and natural."),
    "automotive": ("PRODUCT DETAIL", "Show the actual car accessory clearly in a stationary, safe setting; do not imply unverified compatibility or functions."),
    "garden": ("PRODUCT DETAIL", "Show the actual garden item in a believable setting, focusing on visible construction and a plausible use only."),
    "kitchen": ("PRODUCT DETAIL", "Show the actual kitchen item in a believable, physically plausible setting; demonstrate only functions supported by its visible design."),
    "furniture": ("PRODUCT DETAIL", "Show the actual furniture or decor at realistic scale, highlighting its visible shape, finish and construction."),
    "baby": ("PRODUCT DETAIL", "Show the actual baby or child-care item in a calm, safe setting; do not stage a child in a risky situation."),
    "crafts": ("PRODUCT DETAIL", "Show the actual art or craft item and a simple plausible use without adding unlisted kit contents."),
    "toys": ("PRODUCT DETAIL", "Show the actual toy clearly at a realistic size, with a simple age-appropriate play action only when suitable for the product."),
    "other": ("PRODUCT DETAIL", "Show a close, stable view of a genuinely visible product detail, then return to a clear full-product view."),
}

def _category_safe_storyboard(storyboard, product_type):
    """Replace a curated beat only when it explicitly references unrelated product categories."""
    if not isinstance(storyboard, (list, tuple)):
        return storyboard
    target = _PRODUCT_CATEGORY_GROUP.get(product_type, "other")
    # Unknown category: do not guess which storyboard beats are irrelevant.
    if target == "other":
        return list(storyboard)
    safe = []
    for beat in storyboard:
        if not isinstance(beat, dict):
            safe.append(beat)
            continue
        item = dict(beat)
        text = " ".join((str(item.get("shot", "")), str(item.get("direction", ""))).split()).casefold()
        foreign_markers = [
            marker
            for group, markers in _CATEGORY_MARKERS.items()
            if group != target and not (target == "kitchen" and group == "food")
            for marker in markers
            if marker in text
        ]
        if foreign_markers:
            safe_label, safe_direction = _CATEGORY_SAFE_SHOTS.get(target, _CATEGORY_SAFE_SHOTS["other"])
            item["shot"] = safe_label
            item["direction"] = safe_direction
        safe.append(item)
    return safe

def build_prompt(mode, product, scene, motion, style='auto', duration=10, concept='', product_type='other', storyboard_override=None):
    style = _resolve_auto_style(style, product_type) if mode == 'storyboard' else style
    if duration in (20, 30):
        # Multi-clip outputs are independent 10-second prompts with a shared style
        # and explicit frame continuity. Keep every segment copy-ready on its own.
        total_parts = duration // 10
        segments = [
            _build_single_prompt(
                mode, product, scene, motion, style, part=part,
                concept=concept, product_type=product_type,
                storyboard_override=storyboard_override, total_parts=total_parts,
            )
            for part in range(1, total_parts + 1)
        ]
        return "\n\n".join(
            f"=== KLIPPO PART {part}/{total_parts} ===\n\n{segment}"
            for part, segment in enumerate(segments, start=1)
        )
    return _build_single_prompt(mode, product, scene, motion, style, part=0, concept=concept, product_type=product_type, storyboard_override=storyboard_override)


def _build_single_prompt(mode, product, scene, motion, style='auto', part=0, concept='', product_type='other', storyboard_override=None, total_parts=2):
    duration = 10
    hook_cta_language = "HOOK + CTA: Start with a product-specific visual hook, show one real detail or plausible use, and end with a clear product shot. No added text, logos or watermarks."
    camera = CAMERAS.get(motion, CAMERAS["push"])
    product_type_directions = {
        'fashion': "PRODUCT CATEGORY DIRECTION: Treat this as clothing/fashion. Favor natural fabric movement and visible garment details; never alter cut, print, color or pattern.",
        'bag': "PRODUCT CATEGORY DIRECTION: Treat this as a bag subtype inferred from the product name. Choose a matching presentation (handbag hero, crossbody lifestyle or backpack upright showcase). Do not assume exact materials, compartments, hardware or accessories unless stated in the name.",
        'wallet': "PRODUCT CATEGORY DIRECTION: Treat this as a wallet inferred from the product name. Favor a luxury macro, simple open-close presentation or clean flat lay. Do not assume exact materials, card slots, coin pockets, compartments or capacity.",
        'hijab': "PRODUCT CATEGORY DIRECTION: Treat this as a hijab/tudung. Emphasize the exact drape, folds, texture and visible styling; do not change the wrap, color or fabric pattern.",
        'shoes': "PRODUCT CATEGORY DIRECTION: Treat this as footwear. Favor grounded placement and visible upper/outsole details; do not invent soles or unseen angles.",
        'beauty': "PRODUCT CATEGORY DIRECTION: Treat this as a beauty, cosmetics or skincare product. Favor clean styling, packaging and texture close-ups; do not imply medical results or unverified benefits.",
        'food': "PRODUCT CATEGORY DIRECTION: Treat this as food or drink. Favor appetizing but realistic lighting and visible texture; do not add ingredients, toppings or serving items not shown.",
        'stationery': "PRODUCT CATEGORY DIRECTION: Treat this as stationery or a writing/study item. Show only plausible use, keep paper blank or use abstract marks with no readable generated text, and do not invent included supplies.",
        'sports': "PRODUCT CATEGORY DIRECTION: Treat this as sports or fitness equipment. Keep the item at realistic scale, show only safe and plausible use, and do not invent performance or durability claims.",
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
        'toys': "PRODUCT CATEGORY DIRECTION: Treat this as a toy or play item. Keep play actions age-appropriate and physically plausible; show only the toy and accessories confirmed by the product details.",
        'other': "PRODUCT CATEGORY DIRECTION: Follow the product category inferred from the product name and choose a suitable presentation without guessing features.",
    }
    category_direction = product_type_directions.get(product_type, product_type_directions['other'])
    model_age_direction = _model_age_direction(product, product_type)
    identity = (
        "PRODUCT LOCK: Use the uploaded product photo as the source of truth. Preserve its visible shape, colour, print, packaging, branding and proportions. "
        "Do not invent unseen features, accessories, materials or claims. Keep realistic physical scale."
    )
    art = (
        f"VISUAL STYLE: {scene}. Photorealistic commercial video, natural lighting, realistic texture and shadows, "
        "stable framing and physically plausible movement. Keep the product clear and unchanged."
    )
    negative = (
        "AVOID: distorted product geometry, changing patterns, extra accessories, duplicated items, unnatural hands or faces, "
        "flicker, abrupt transitions, fake reflections, added captions, subtitles, logos or watermarks."
    )
    if mode == "storyboard":
        style_key, style_name, style_template = resolve(style)
        doodle = style_key == "white_doodle"
        hook = product_hook(product)
        evidence_rules = "Use only details visible in or confirmed by the product reference. Do not invent features or claims."

        hook_direction = (
            "VISUAL HOOK: Open with a product-specific reveal or plausible action in the first 2 seconds; use only supported product details. "
        ) if hook else (
            "Open with a clear product reveal and use composition or action as the hook. Do not guess product benefits or claims."
        )
        if storyboard_override:
            hook_direction = "Follow the selected product-specific storyboard."
        if doodle:
            if part > 1:
                rules = (
                    "CONTINUATION CLIP 10s, five 2-second panels: 0-2s resume from the exact final full-product framing of the preceding clip; "
                    "2-4s begin drawing a thin white dashed contour just OUTSIDE the actual product silhouette; "
                    "following only visible product edges; 4-6s complete and hold the contour. "
                    "6-8s add one small white dotted arrow or sparkle beside a genuinely visible detail; "
                    "8-10s clean full-product hero packshot; if another clip follows, hold the exact final frame without a fade, otherwise finish with a gentle fade. Do NOT repeat the preceding clip hook. "
                )
            else:
                rules = (
                    "FIRST CLIP 10s, five 2-second panels: 0-2s close-up with a verified product-name/category hook if available; "
                    "2-4s full product reveal; 4-6s one genuinely visible detail; 6-8s restrained white doodle emphasis; "
                    "8-10s settle into a steady full-product composition and HOLD the exact final frame for a seamless next-clip handoff. "
                    "Do not perform the main surrounding contour yet. "
                )
            rules += (
                "Warm authentic UGC product-ad look, thin white handwritten 2D graphics tracked to the product. "
                "No phone bezel, no invented product claims, and no branding obstruction. "
                "Use only flat visual lines, simple arrows and small sparkles; no letters, words, feature labels or captions. "
                "Keep graphics clear of the product and prioritize tracing its actual visible contour over camera movement."
            )
        elif part > 1:
            rules = (
                "CONTINUATION CLIP 10s, five 2-second panels: 0-2s continue the exact full-product frame held at the end of the preceding clip; "
                "2-4s emphasize a second genuinely visible detail without inventing an angle; 4-6s continue the same concept; "
                "6-8s elegant style-specific visual emphasis; 8-10s full-product hero closing. If another clip follows, hold the exact final frame without a fade; otherwise finish with a gentle fade. Do NOT repeat the preceding clip hook."
            )
        else:
            rules = (
                "FIRST CLIP 10s, five 2-second panels: 0-2s verified product-name/category hook if available; "
                "2-4s full-product reveal; 4-6s one genuinely visible detail; 6-8s continue the product story; "
                "8-10s settle into a stable full-product frame and HOLD for a seamless next-clip handoff. No closing fade in this segment."
            )
        curated_direction = ""
        if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
            curated_shots = _category_safe_storyboard(storyboard_override, product_type)
            if part > 1:
                curated_shots = [
                    {
                        "time": "0–2s",
                        "shot": "CONTINUITY BRIDGE",
                        "direction": (
                            "Continue from the exact final frame of the preceding clip. Preserve the same product identity and true scale, "
                            "hand/model, wardrobe, voice, lighting, setting and camera direction. Make only a small natural "
                            "continuation movement; do not restart the reveal or repeat the preceding clip's hook or dialogue."
                        ),
                    },
                    {
                        "time": "2–6s",
                        "shot": "SECONDARY DEMONSTRATION",
                        "direction": (
                            "Show a distinct action or product angle not used in the immediately preceding clip. Follow the selected "
                            "concept and product category, but do not repeat the first clip's main interaction, camera move or "
                            "dialogue. Use only visible, plausible features and props; if no functional action is suitable, "
                            "show a different reference-supported view of the actual product."
                        ),
                    },
                    {
                        "time": "6–8s",
                        "shot": "ALTERNATE DETAIL / TRUST SHOT",
                        "direction": (
                            "Reveal a different visible detail from the preceding clip, if one is supported by the reference; otherwise "
                            "use a new reference-supported angle. Use macro framing rather than changing physical size. "
                            "Do not invent materials, components, benefits or specifications."
                        ),
                    },
                    {
                        "time": "8–10s",
                        "shot": "FINAL HERO / SPOKEN CTA",
                        "direction": (
                            "Finish on a clear full-product hero at the same true scale and in the same coherent setting. "
                            "End with the selected voiceover CTA; never show CTA text on screen. "
                            "Do not repeat the previous clip's hook or closing line."
                        ),
                    },
                ]
            curated_direction = (
                "DIRECTOR'S CURATED PREMIUM STORYBOARD: Use this selected GitHub library storyboard as the primary shot plan. "
                + (("CONTINUATION SEGMENT " + str(part) + "/" + str(total_parts) + ": Use a fresh, product-specific continuation hook and a distinct action not used in earlier clips; do not repeat earlier CTA wording. Preserve the exact previous final frame at 0–2s. ") if part > 1 else "")
                + "Follow the four selected beats in order, fitting them naturally into 10 seconds. Keep product identity, model and setting consistent. "
                + "\n\n".join(
                    str(item.get("time", "")) + " | " + str(item.get("shot", "")) + "\n"
                    + str(item.get("direction", ""))
                    for item in curated_shots
                )
            )
        storyboard_plan = (
            curated_direction if curated_direction else
            (hook_direction if part != 2 else "NO REPEATED OPENING HOOK in Part 2.") + "\n\n" + rules
        )
        return (
            "PROMPT VIDEO — 10 SAAT\n"
            + "Vertical 9:16, " + str(duration) + " seconds. " + style_name + ".\n"
            + "Style direction: " + " ".join(str(style_template).split())[:220].rstrip() + ".\n"
            + "Product: " + product + ". " + category_direction + (" " + model_age_direction if model_age_direction else "") + "\n"
            + "Setting: " + scene + ". Camera: " + camera + "\n"
            + "PRODUCT LOCK: Preserve the reference product's visible design, colour, pattern, branding and proportions. Do not invent features or accessories.\n"
            + "HOOK + CTA: Open with a product-specific hook, show one relevant detail or plausible use, and finish on a clear product shot.\n\n"
            + "STORYBOARD:\n" + storyboard_plan + "\n\n"
            + ("CREATIVE IDEA: " + concept.strip() + "\n\n" if concept else "")
            + ("WHITE DOODLE: Keep selected doodles small and outside the product silhouette; use no letters or labels.\n" if doodle else "")
            + "Keep actions, lighting and camera movement natural and consistent. Follow the selected storyboard and visual options."
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
    elif part > 1:
        direction = ("CONTINUATION CLIP 10s, five 2-second panels: start with the EXACT held full-product final frame from the preceding clip, "
                     "matching crop, product position, orientation, setting, lighting and color. "
                     "0-2s resume the same movement; 2-4s continue with a distinct action; 4-6s highlight another visible detail; "
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
    if mode == "storyboard":
        # Compact, copy-ready storyboard: short sentences, selected choices, no generic option branches.
        style_key, style_name, style_template = resolve(style)
        selected_beats = []
        if storyboard_override and isinstance(storyboard_override, (list, tuple)):
            safe_override = _category_safe_storyboard(storyboard_override, product_type)
            for beat in safe_override[:4]:
                if isinstance(beat, dict):
                    time_label = str(beat.get("time", "")).strip()
                    shot_label = str(beat.get("shot", "")).strip()
                    beat_text = " ".join(str(beat.get("direction", "")).split())
                    if time_label or shot_label or beat_text:
                        selected_beats.append((time_label + " " + shot_label + ". " + beat_text).strip())
                else:
                    beat_text = " ".join(str(beat).split())
                    if beat_text:
                        selected_beats.append(beat_text)
        if not selected_beats:
            selected_beats = [
                "Open with an engaging close-up without changing the product's appearance.",
                "Reveal the full product in the selected setting, preserving its exact scale and colour.",
                "Show one genuinely visible detail using the selected camera movement.",
                "Finish with a clear, steady full-product shot as the visual CTA."
            ]
        # Keep every segment under Telegram's one-message limit while retaining selected storyboard beats.
        selected_beats = [" ".join(str(x).split())[:420].rstrip() for x in selected_beats[:4]]
        if part > 1:
            selected_beats = [
                "Continue from the exact final frame of the previous clip. Keep the same product, model, outfit, setting and lighting while the action moves naturally forward.",
                "Show a distinct follow-up action that matches the selected style and idea. Do not repeat the previous clip's opening.",
                "Highlight another visible product detail, or use a safe angle without inventing features.",
                "Finish with a full-product shot and the selected voiceover CTA or visual action."
            ]
        elif part == 1 and total_parts > 1:
            selected_beats[-1] = selected_beats[-1].rstrip(".") + ". Hold the final frame without fading so the next clip connects seamlessly."
        elif total_parts == 1:
            selected_beats[-1] = selected_beats[-1].rstrip(".") + ". End on a clear, steady product shot."
        scene_lines = []
        for i, beat in enumerate(selected_beats, start=1):
            start_s = (i - 1) * 10 / len(selected_beats)
            end_s = i * 10 / len(selected_beats)
            scene_lines.append(f"Shot {i} ({start_s:g}–{end_s:g}s): {beat}")
        compact_lines = [
            "KLIPPO | PRODUCT VIDEO STORYBOARD",
            f"Format: vertical 9:16. Exact duration: 10 seconds" + (f". Part {part}/{total_parts}." if part else "."),
            f"Product: {product}.",
            f"Visual style: {style_name}. {' '.join(str(style_template).split())[:260].rstrip()}. Setting: {scene}.",
            f"Camera movement: {motion}.",
            category_direction,
        ]
        if model_age_direction:
            compact_lines.append(model_age_direction)
        compact_lines.extend([
            "Preserve the product's exact shape, colour, pattern, packaging, original branding and real-world scale. Do not invent unseen features, materials or accessories.",
            *scene_lines,
            "Create photorealistic footage with natural movement, believable lighting and shadows. Add no text, captions, logos or watermarks."
        ])
        if concept:
            compact_lines.insert(5, "User-selected idea: " + " ".join(str(concept).split())[:350].rstrip(".") + ".")
        return "\n".join(line for line in compact_lines if line and line.strip())
    return (
        "KLIPPO | PROFESSIONAL IMAGE-TO-VIDEO PRODUCTION PROMPT" + (" | BAHAGIAN " + str(part) + "/" + str(total_parts) if part else "") + "\n"
        "OUTPUT: " + str(duration) + " seconds; portrait 9:16; high-quality realistic product commercial; "
        + hook_cta_language + "\n\n"
        "one coherent deliverable. NO ON-SCREEN TEXT: Do not generate captions, headlines, labels, subtitles, UI overlays, added logos or watermarks. Use a visual hook through composition and action only; any selected hook or CTA must be spoken audio, never written on screen. Preserve only branding physically present on the actual reference product.\n\n"
        "PRODUCT: " + product + "\n" + category_direction + "\n" + model_age_direction + "\n\n" + identity + "\n\n" + art + "\n\n"
        + direction + "\n\n" + negative + "\n\n"
        "HOOK + DEMONSTRATION + CTA: Open with a product-specific visual hook, show one reference-supported detail or use, and finish with a clear hero shot. Keep all hook/CTA communication in the selected audio direction; never display it as text. " +
        "FINAL REALISM CHECK: The result should pass as authentic live-action commercial footage at first glance, not as an AI-generated image or animation. Consistent product identity in every frame, realistic skin and hand anatomy if a person appears, natural fabric or material texture, grounded contact shadows, plausible reflections, stable exposure, real-camera perspective and physically possible movement. Avoid the polished-but-fake CGI look, artificial skin smoothing, impossible object motion, warped geometry, flicker and temporal identity drift. "
        "FINAL QUALITY CHECK: Consistent identity in every frame, natural physics, clean edges, "
        "stable illumination, smooth temporal coherence and polished affiliate-ad aesthetics. "
        "If the product name does not support a requested feature or viewpoint, use a safe crop or modest "
        "2D camera movement instead of hallucinating the product."
    )