from prompt_catalog import resolve, product_hook, opening_direction
import json
from pathlib import Path

"""Detailed, reference-safe AI video prompt templates for KLIPPO."""

UNIVERSAL_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "universal_prompt_templates.json"
try:
    with UNIVERSAL_PROMPT_PATH.open("r", encoding="utf-8") as _handle:
        _universal_data = json.load(_handle)
    UNIVERSAL_PROMPT_FRAMEWORKS = _universal_data.get("frameworks", [])
    UNIVERSAL_PROMPT_GLOBAL_RULES = _universal_data.get("global_rules", [])
except (OSError, json.JSONDecodeError):
    UNIVERSAL_PROMPT_FRAMEWORKS = []
    UNIVERSAL_PROMPT_GLOBAL_RULES = []


def _universal_prompt_direction(style_key):
    """Return a style-matched universal framework for custom categories, without an AI/API call."""
    for framework in UNIVERSAL_PROMPT_FRAMEWORKS:
        if style_key in framework.get("style_keys", []):
            return str(framework.get("direction", "")).strip()
    return str(UNIVERSAL_PROMPT_FRAMEWORKS[0].get("direction", "")).strip() if UNIVERSAL_PROMPT_FRAMEWORKS else (
        "Use a clean product reveal, one subtle camera move, one genuinely visible detail and a stable full-product finish. "
        "Preserve the reference and never invent product facts."
    )


def _universal_prompt_rules():
    return " ".join(str(rule).strip() for rule in UNIVERSAL_PROMPT_GLOBAL_RULES if str(rule).strip())



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


def build_prompt(mode, product, scene, motion, style='auto', duration=10, concept='', product_type='other', storyboard_override=None, split=None, universal_custom=False):
    # Preserve the historical API behavior: a 20-second call without an explicit
    # split choice still returns two connected 10-second prompts.
    if split is None:
        split = duration in (20, 30)
    style = _resolve_auto_style(style, product_type) if mode == 'storyboard' else style
    if split and duration > 10:
        # Generate connected 10-second prompts while retaining the same style and product context.
        parts = [
            _build_single_prompt(mode, product, scene, motion, style, part=index, duration=10,
                                 concept=concept, product_type=product_type, storyboard_override=storyboard_override, universal_custom=universal_custom)
            for index in range(1, duration // 10 + 1)
        ]
        return "\n\n".join(
            ("=== KLIPPO PART " + str(index + 1) + " ===\n\n" + part) if index else part
            for index, part in enumerate(parts)
        )
    return _build_single_prompt(mode, product, scene, motion, style, part=0, duration=duration,
                                concept=concept, product_type=product_type, storyboard_override=storyboard_override, universal_custom=universal_custom)


def _build_single_prompt(mode, product, scene, motion, style='auto', part=0, duration=10, concept='', product_type='other', storyboard_override=None, universal_custom=False):
    scene_text = str(scene or '').lower()
    selected_scene_lock = "STRICT LOCATION LOCK: The user-selected location is exactly: " + str(scene or "a realistic setting suited to the product") + ". Keep every scene in this location. Do not change it to an airport, terminal, mall, studio, home or any other place unless that place is explicitly the selected location. Product category must never override the selected location. "
    if motion in ('auto', '', None):
        if any(term in scene_text for term in ('mirror', 'vanity', 'dressing table', 'cermin')):
            camera = "Use a stable medium framing that follows the model's small natural movements, then a gentle side adjustment to include the mirror reflection; never circle around the model or distort the reflection."
        elif any(term in scene_text for term in ('airport', 'terminal', 'mall', 'shopping mall', 'street', 'beach', 'garden', 'park')):
            camera = "Use a smooth tracking shot from the front three-quarter or side as the person walks naturally; keep pace and distance steady, with no forced product rotation."
        elif any(term in scene_text for term in ('cafe', 'restaurant', 'living room', 'bedroom', 'home interior', 'hotel')):
            camera = "Begin with a calm medium-wide contextual view, then make a gentle push-in only when the person naturally uses or presents the product."
        elif any(term in scene_text for term in ('kitchen', 'workshop', 'office', 'library')):
            camera = "Use a steady practical demonstration angle, with a subtle close-in on the actual interaction and no distracting camera orbit."
        elif product_type in ('beauty', 'wallet', 'accessory', 'gadget'):
            camera = "Use a restrained close-in to show visible product details, then hold a clear stable view; preserve product shape and markings."
        elif product_type in ('fashion', 'hijab', 'shoes', 'bag', 'travel'):
            camera = "Use a smooth medium shot with a short natural walk or body movement, tracking gently only as needed to keep the product visible."
        else:
            camera = "Choose one restrained camera movement suited to the product and action; prioritize a clear stable view and believable perspective."
    else:
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
    category_direction += selected_scene_lock
    if part in (0, 1):
        category_direction += " " + opening_direction(product_type)
    natural_motion_by_type = {
        'bag': "If a human model is present, have them carry the bag as a real person would and act naturally in the SELECTED LOCATION: use relaxed shoulders, natural arm swing and subtle bag sway if walking; if seated or stationary, keep the bag held or worn naturally. Only mention an airport, terminal or check-in area when the user explicitly selected an airport setting. Never stand rigidly while rotating or twirling the handbag for the camera.",
        'fashion': "If a model is present, use a relaxed short walk, natural weight shifts and a small practical gesture such as adjusting a sleeve or letting the fabric settle. Avoid stiff runway posing unless runway style is explicitly requested.",
        'hijab': "If a model is present, use a relaxed walk or gentle head turn, with natural fabric settling. Do not repeatedly touch, pull or spin the hijab unnaturally.",
        'shoes': "If a model is present, show a few natural steps with believable foot contact and weight transfer; keep the shoes visible without exaggerated foot lifting or robotic marching.",
        'wallet': "Prefer a believable hand-held demonstration: pick up, open only if the reference supports it, and return to a relaxed hold. No repeated spinning or impossible finger movement.",
        'beauty': "Use calm, small hand movements and plausible product handling. Do not repeatedly rotate the container or apply it to skin unless the action is appropriate and supported by the reference.",
        'food': "Use natural serving or handling motion only when suitable; preserve the actual food and do not make it morph, bounce or multiply.",
        'gadget': "Use deliberate, minimal hand interaction with controls that are actually visible. Avoid random tapping, turning the device over repeatedly or inventing interface behavior.",
        'home': "Show the product in a believable everyday context with one practical, physically possible interaction; preserve scale and contact with surrounding surfaces.",
        'travel': "Use natural walking or packing movement with believable handling and weight. Do not swing, spin or teleport luggage or travel gear.",
        'accessory': "Use subtle, anatomically plausible handling or wearing motion; no repeated twirling, exaggerated wrist turns or floating product movement.",
        'other': "If a person is present, give them one simple, purposeful action suited to the product and location. Prefer natural walking or practical interaction over static posing with repetitive product rotation.",
    }
    # Let the product, not a default full-body shot, determine framing.
    framing_by_type = {
        'shoes': " FRAMING PRIORITY — FOOTWEAR: Keep the frame low and focused on the worn shoes and lower legs; the model's face and full body are not needed. Use a close or medium-close view that clearly shows the shoes while preserving believable foot placement and proportions. ",
        'accessory': " FRAMING PRIORITY — ACCESSORIES: Use close or medium-close framing around the body area where the accessory is worn; do not force a full-body shot. ",
        'beauty': " FRAMING PRIORITY — BEAUTY: Prioritize the product and the relevant hand or application area; show the face only when useful for the actual product action. ",
        'wallet': " FRAMING PRIORITY — WALLET: Prioritize the wallet and hands; the model's face and full body are unnecessary. ",
        'bag': " FRAMING PRIORITY — BAG: Keep the bag clearly visible in a natural hand-held, worn or placed composition; choose a medium or close framing that suits the selected action. ",
        'gadget': " FRAMING PRIORITY — GADGET: Prioritize the device and the hands interacting with it; do not require a full-body or face shot. ",
    }
    category_direction += framing_by_type.get(product_type, "")
    if product_type == 'shoes' and any(term in scene_text for term in ('car', 'vehicle', 'kereta', 'automobile')):
        category_direction += (
            " CAR SCENE — SHOE DETAIL: Show the model seated in a stationary parked car, with the camera aimed down toward the shoes being worn and the lower legs. Keep the shoes as the clear subject; the face and full body stay outside the frame. The model may gently reposition one foot or angle the shoes naturally toward the camera. Keep the vehicle stationary, hands away from driving controls, and never show unsafe filming while driving. Do not turn this into a mirror selfie or show a phone in the model's hand. " 
        )
    category_direction += " NATURAL HUMAN MOVEMENT: " + natural_motion_by_type.get(product_type, natural_motion_by_type['other']) + " "
    scene_action_directions = [
        (('mirror' in scene_text or 'vanity' in scene_text or 'dressing table' in scene_text or 'cermin' in scene_text),
         "SCENE ACTION — MIRROR: If a model is present, let them look at their reflection, make one small practical adjustment to the outfit or hijab if relevant, and optionally turn naturally once to check the side view. The reflection and body movement must remain physically consistent; no repeated spinning."),
        (('airport' in scene_text or 'terminal' in scene_text),
         "SCENE ACTION — AIRPORT: If suitable for the product, have the model walk naturally toward the terminal or past the check-in area. Use relaxed shoulders, natural arm swing and believable product movement; do not pose rigidly or twirl a bag."),
        (('boutique' in scene_text or 'shop' in scene_text or 'mall' in scene_text),
         "SCENE ACTION — SHOPPING: Use a simple purposeful action such as browsing a rack, taking a few steps or pausing to present the product. Keep background shoppers subtle and avoid distracting interactions."),
        (('cafe' in scene_text or 'restaurant' in scene_text),
         "SCENE ACTION — CAFE/RESTAURANT: Prefer a relaxed seated or standing interaction that fits the product; use natural hand placement and do not make the model perform unrelated gestures."),
        (('kitchen' in scene_text or 'bakery' in scene_text),
         "SCENE ACTION — KITCHEN: Show one plausible preparation, serving or practical-use action only when the product supports it. Keep food, hands and utensils physically consistent."),
        (('garden' in scene_text or 'beach' in scene_text or 'nature' in scene_text or 'park' in scene_text),
         "SCENE ACTION — OUTDOORS: Use a gentle walk, a natural pause or a relevant practical interaction. Let clothing and loose items respond subtly to movement and breeze without exaggerated motion."),
        (('office' in scene_text or 'library' in scene_text or 'workshop' in scene_text),
         "SCENE ACTION — WORKSPACE: Prefer a focused, practical product interaction at a desk or work surface; maintain believable contact with objects and keep the product clearly visible."),
    ]
    for scene_matches, direction in scene_action_directions:
        if scene_matches:
            category_direction += " " + direction
            break
    category_direction += (
        " PRODUCT-SPECIFIC SPOKEN COPY: Only if voice-over or dialogue is explicitly requested, write a short, conversational line about this exact product category and only visible or verified features. "
        "Do not repeat generic phrases such as 'perincian teliti', 'lihat dengan dekat' or 'sangat terperinci'; do not narrate camera directions. "
        "MALAYSIAN MALAY VOICE AND PRONUNCIATION: When Malay speech is requested, use a native-sounding Bahasa Melayu Malaysia accent and standard Malaysian pronunciation, clearly articulated at a natural, moderate pace. "
        "Use Malaysian vocabulary, sentence structure and everyday phrasing; do not use Indonesian slang, Indonesian vocabulary, Indonesian accent, Indonesian intonation or Indonesian-style pronunciation. "
        "Avoid Indonesian wording such as 'kebutuhan', 'temukan', 'silakan', 'banget', 'nggak' and 'aja'; use natural Malaysian equivalents where needed. Do not exaggerate any regional Malaysian dialect unless the user explicitly requests it. "
        "If the user supplies an exact script, preserve its words and meaning; pronounce it clearly in a Malaysian Malay accent without adding Indonesian expressions. "
        "Vary both the wording and the opening approach across generations: sometimes begin with a relevant visual demonstration, sometimes a short product-specific line, and sometimes a clean reveal with no hook. "
        "Avoid classroom-style introductions, repetitive stock phrases and scripted-sounding language. Use a natural, concise Malaysian-Malay advertising tone. Never invent materials, benefits, quality, comfort or specifications. "
        " STRICT NO-LOGO RULE: Do not add any logo or watermark anywhere in the video, including TikTok, Shopee, creator, AI-generator or provider branding; "
        "no logo overlays, corner bugs, end cards, branded borders, platform UI or background signage. Never add captions or text unless separately requested. "
        "If a logo or mark is physically printed on the reference product, preserve it only as part of that exact product and never create a separate or enlarged logo."
    )
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
        if product_type == "other" or universal_custom:
            category_direction += (
                " UNIVERSAL CREATIVE FRAMEWORK: "
                + _universal_prompt_direction(style_key)
                + " UNIVERSAL SAFETY RULES: "
                + _universal_prompt_rules()
            )

        # Keep single 10-second prompts concise enough for one Telegram message.
        # Retain the selected style, reference safety, timed beats and user concept.
        if duration in (10, 20, 30) and (duration == 10 or part == 0):
            if duration == 10 and part >= 2:
                clip_label = "SECOND CLIP 10s" if part == 2 else "CONTINUATION CLIP 10s"
                beat_plan = (clip_label + ": 0–2s continue from the exact full-product frame held at the end of the previous clip; "
                             "2–4s resume the same movement; 4–6s show another visible detail; 6–8s continue in the same setting; "
                             "8–10s stable full-product hero finish. Do NOT repeat the opening hook. ")
            elif duration == 10 and part == 1:
                beat_plan = ("FIRST CLIP 10s: 0–2s establish the product; 2–4s reveal it fully; 4–6s highlight one visible detail; "
                             "6–8s continue one simple action; 8–10s HOLD the final frame for Part 2. No fade. ")
            elif duration == 20:
                beat_plan = ("TIMING: 0–4s clear product reveal; 4–8s show the complete product in its setting; "
                             "8–12s highlight one genuinely visible detail; 12–16s one subtle category-appropriate action; "
                             "16–20s stable full-product hero finish. ")
            elif duration == 30:
                beat_plan = ("TIMING: 0–6s clear product reveal; 6–12s show the complete product in its setting; "
                             "12–18s highlight one genuinely visible detail; 18–24s one subtle category-appropriate action; "
                             "24–30s stable full-product hero finish. ")
            else:
                beat_plan = ("TIMING: 0–2s clean reveal; 2–4s show the full product; 4–6s highlight one reference-visible detail; "
                             "6–8s one subtle product-appropriate action; 8–10s HOLD the final frame in a full-product hero composition. "
                             + ("Do not perform the main surrounding contour yet. " if doodle else ""))
            if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
                beat_plan = (
                    "DIRECTOR'S CURATED PREMIUM STORYBOARD: NO ON-SCREEN TEXT. "
                    + (("CONTINUITY BRIDGE: Resume from Part 1's exact final product frame. "
                        "CONTINUATION ACTION: Continue the same concept. Do not repeat the opening hook. ")
                       if part == 2 else "")
                    + "FOLLOW THESE SELECTED STORYBOARD BEATS IN ORDER: "
                    + " | ".join(
                        str(item.get("shot", "")) + ": " + str(item.get("direction", ""))
                        for item in storyboard_override
                    ) + ". "
                )
            hook_rule = (
                "NO ON-SCREEN TEXT: Do not render product names, headlines, captions, labels, logos or watermarks. "
                + ("If voiceover is enabled, an optional natural spoken opening may say: '" + hook + "'. Do not force dialogue. "
                   if hook and not storyboard_override and part < 2 else
                   "Use a clean visual reveal; dialogue is optional. ")
            )
            doodle_rule = (
                "GRAPHICS: Thin white hand-drawn marks may emphasize visible product edges only; never cover the product. "
                if doodle else ""
            )
            concept_rule = ("CREATIVE IDEA: " + concept.strip() + ". " if concept and concept.strip() else "")
            return (
                "PROMPT VIDEO — " + str(duration) + " SAAT" + (" | BAHAGIAN " + str(part) if part else "") + "\n"
                "Vertical 9:16, one realistic product ad, target 1080x1920, highest available native quality, crisp visible product detail, natural colour and exposure, low noise, stable frame-to-frame geometry, composed for Shopee/TikTok full-screen mobile viewing with the product inside the safe area, exactly " + str(duration) + " seconds.\n"
                "PRODUCT: " + product + "\n"
                + category_direction + "\n"
                + "STYLE: " + style_name + " — " + style_template[:450] + "\n"
                + "SETTING: " + scene[:300] + ". CAMERA: " + camera + "\n"
                + hook_rule + beat_plan + concept_rule[:400] + doodle_rule
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
            "NO ON-SCREEN TEXT: Do not render product names, headlines, captions, labels, logos or watermarks. "
            + ("If voiceover is enabled, an optional natural spoken opening may say: '" + hook + "'. Do not force dialogue. "
               if hook else
               "Begin with a clean visual product reveal; dialogue is optional. ")
            + "Never invent a category, benefit, price, popularity or product name."
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
                    "FIRST CLIP 10s, five 2-second panels: 0-2s clean visual close-up with no on-screen text; "
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
                "FIRST CLIP 10s, five 2-second panels: 0-2s clean visual product reveal with no on-screen text; "
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
                ("NATURAL PRODUCT ACTION", "Show one simple, purposeful action that fits this exact product and location. If a person is present, use relaxed, anatomically plausible movement and natural weight transfer; choose a short walk or practical interaction where appropriate. Never make the model stand rigidly while repeatedly spinning, twirling or rotating the product. Avoid robotic posing, exaggerated gestures and impossible hand movements."),
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
            "OUTPUT: One cohesive vertical 9:16 product advertisement, target resolution 1080x1920, highest available native quality, crisp product detail, natural colour and exposure, low noise, stable frame-to-frame geometry, composed for Shopee/TikTok full-screen mobile viewing with the product inside the safe area, EXACT DURATION: " + str(duration) + " seconds.\n\n"
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
            "DIRECTOR'S NATURAL FASHION TRY-ON BRIEF: Create one continuous, believable 10-second vertical fashion product video with realistic skin and fabric texture. "
            "Keep the model's appearance and outfit consistent. Unless the user explicitly selected a mirror-selfie concept, the model must NOT hold a phone, film themselves, pose for a mirror selfie or behave as the camera operator. "
            "Use an external camera operated by an unseen videographer. Follow the exact user-selected location; never replace it with a home, bedroom or dressing room. "
            "0–2s | ESTABLISH: Show the model and full outfit naturally within the selected location. "
            "2–5s | NATURAL ACTION: Use one small, relaxed action suited to the location, such as a short walk, a natural pause or a subtle adjustment to a sleeve or garment. Keep both hands naturally placed unless the product action requires otherwise. "
            "5–8s | OUTFIT DETAIL: Let the external camera move subtly to show visible garment details without cropping away the product or fabric unnaturally. "
            "8–10s | FINISH: Settle into a relaxed, natural pose and hold briefly. Keep movement human and physically plausible; no dancing, exaggerated posing or scene changes. "
            "FASHION PRODUCT LOCK: The exact garment must remain unchanged frame to frame—same color, print, pattern placement, neckline, sleeves, cut, fit, fabric, accessories and proportions. "
            "Keep the chosen hijab style and handbag presentation consistent. Never redesign, recolor, reshape, add or remove stated outfit details. "
            "Use the selected location's lighting and surroundings. No collage, split screen, poster layout, outfit change, plastic skin or CGI. " + selected_scene_lock
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
