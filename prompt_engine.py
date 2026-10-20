from prompt_catalog import resolve, product_hook, opening_direction
import json
from pathlib import Path

import random
import re
from collections import deque

def _prompt_sentence(value, limit=100, fallback=""):
    """Keep complete, meaningful sentences; the limit is a target, not a destructive cut."""
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return fallback
    if len(text) <= limit:
        return text
    sentences = [part.strip() for part in re.findall(r".+?(?:[.!?](?=\s|$)|$)", text) if part.strip()]
    if not sentences:
        return fallback
    # Never discard a distinctive first sentence just because it exceeds the target.
    kept = [sentences[0]]
    if len(kept[0]) < limit:
        for sentence in sentences[1:]:
            candidate = " ".join(kept + [sentence])
            if len(candidate) > limit:
                break
            kept.append(sentence)
    return " ".join(kept)


# Keep recent action choices in memory so consecutive prompts vary naturally.
_RECENT_CREATIVE_CHOICES = {}
_CREATIVE_ACTIONS = {
    "fashion": [
        "Begin in a three-quarter view; the model glances at the outfit, takes two small natural steps and settles into a relaxed pose.",
        "Begin with a side profile; the model gently turns to a front-facing full-outfit view, keeping the garment visible.",
        "Begin with a candid glance away from camera; the model walks diagonally across frame and pauses for a full-outfit reveal.",
        "Begin on a visible garment detail, then smoothly widen to reveal the model already moving naturally.",
        "The model makes one small playful half-turn, then returns to a clear front view; no exaggerated posing.",
        "The model shifts weight naturally and takes one step sideways while the camera tracks gently in the opposite direction."
    ],
    "bag": [
        "Start with the bag resting naturally; a hand lifts it once by an existing visible handle or strap.",
        "Use a slow side approach as the bag is picked up and held still for a clear silhouette.",
        "Begin with a three-quarter product view, then gently reposition only to show reference-visible details.",
        "Show the bag in a plausible everyday carrying position, then settle into a stable product hero view."
    ],
    "shoes": [
        "Begin at a low three-quarter angle; one foot takes a small step forward and pauses.",
        "Track a short, natural two-step walk, then hold on both shoes without changing their design.",
        "Start with both shoes grounded; make a gentle lateral camera move to reveal their visible profile."
    ],
    "beauty": [
        "Begin with clean packaging hero framing, then make a slow macro push toward one genuinely visible detail.",
        "Use a gentle side-light sweep across the package, then settle into a sharp front-facing view.",
        "Begin slightly off-centre and make a controlled lateral slide into a balanced hero composition."
    ],
    "food": [
        "Begin with the complete serving in view, then make a slow push-in toward a visible texture.",
        "Use a gentle overhead-to-oblique camera drift without adding ingredients or changing the serving.",
        "Start on a close texture detail, then ease out to show the full original serving."
    ],
    "gadget": [
        "Begin with a three-quarter front view, then slide laterally to reveal only visible ports and controls.",
        "Use a locked product shot with a subtle focus shift to one visible detail.",
        "Begin wider, then perform a restrained push-in while keeping screen content and geometry unchanged."
    ],
    "wallet": [
        "Begin with the wallet closed and fully visible, then let a hand pick it up once for a steady close view.",
        "Use a clean flat-lay and a slow camera slide across only visible stitching, edges or closure details.",
        "Open the wallet only if the reference supports it, show the actual visible interior briefly, then close it naturally."
    ],
    "pet": [
        "Keep the pet calm and natural; show one brief, safe interaction with the product only when suitable for the species.",
        "Begin with the product clearly visible beside the animal, then use a gentle side-follow of natural movement.",
        "Use a quiet close view of the animal naturally approaching or resting near the product; do not force a trick."
    ],
    "home": [
        "Show one practical, physically plausible interaction with the product, then hold a clean full-product view.",
        "Begin with a tidy contextual wide shot and slide gently toward one visible design detail.",
        "Keep the product grounded on a suitable surface; use a restrained push-in instead of inventing a function."
    ],
    "general": [
        "Start with a clean wide hero composition, then use a gentle lateral slide to reveal a visible detail.",
        "Begin with a close view of a reference-visible feature, then pull back to show the complete product.",
        "Use a restrained three-quarter camera approach and settle into a clear, stable hero frame.",
        "Begin with the product already in the scene; let natural light shift subtly while the camera moves sideways."
    ]
}
_SFX_BY_TYPE = {
    "fashion": "Add a very soft fabric swish only if fabric movement is visible, with light upbeat music at low volume.",
    "bag": "Add a subtle handling rustle only if handling is shown; do not imply an unverified material.",
    "shoes": "Add quiet natural footsteps only when walking is shown, with soft background music.",
    "beauty": "A tiny pop or delicate chime may accent the reveal once; keep it subtle, not cartoonish.",
    "food": "Use a gentle natural sound only if the visible action supports it; avoid exaggerated or invented sounds.",
    "gadget": "Use one restrained digital tick or soft chime at the detail reveal; no fake interface beeps.",
    "wallet": "Use a soft handling sound only if a hand moves the wallet; keep music low and polished.",
    "pet": "Use gentle natural paw, collar or movement sounds only if visible and plausible; never force animal sounds.",
    "home": "Use a quiet handling or placement sound only when the action is visible; keep music soft.",
    "general": "Use one subtle soft chime, tiny pop or gentle whoosh at a matching visual beat; never stack effects."
}


def _creative_variation(product_type, product, part, product_subtype=''):
    """Add one short, category-aware variation and matching audio direction."""
    words = " ".join(str(value or "") for value in (product_type, product_subtype, product)).casefold()
    type_key = str(product_type or "").casefold()
    subtype_key = str(product_subtype or "").casefold()
    if type_key in {"fashion", "hijab"} or any(w in words for w in ("dress", "clothing", "fashion", "apparel", "outfit", "garment", "pakaian", "baju", "skirt", "shirt", "t-shirt", "hijab", "tudung", "blouse")):
        group = "fashion"
    elif type_key == "bag" and (subtype_key in {"bag_wallet", "wallet", "card_holder"} or any(w in words for w in ("wallet", "dompet", "card holder", "cardholder", "coin purse"))):
        group = "wallet"
    elif type_key in {"bag", "travel"} or any(w in words for w in ("bag", "handbag", "backpack", "purse", "luggage", "beg galas", "beg tangan")):
        group = "bag"
    elif type_key == "shoes" or any(w in words for w in ("shoe", "sneaker", "sandal", "footwear", "kasut", "selipar")):
        group = "shoes"
    elif type_key == "pet" or any(w in words for w in ("pet", "kucing", "anjing", "arnab", "rabbit", "hamster", "bird cage", "fish tank", "haiwan")):
        group = "pet"
    elif type_key == "beauty" or any(w in words for w in ("beauty", "cosmetic", "skincare", "perfume", "lipstick", "makeup", "serum")):
        group = "beauty"
    elif type_key == "food" or any(w in words for w in ("food", "drink", "snack", "cake", "coffee", "tea", "makanan", "minuman")):
        group = "food"
    elif type_key in {"gadget", "equipment", "automotive", "office"} or any(w in words for w in ("gadget", "phone", "camera", "earbud", "keyboard", "electronic", "telefon", "gajet")):
        group = "gadget"
    elif type_key in {"home", "kitchen", "furniture", "garden"}:
        group = "home"
    else:
        group = "general"

    options = _CREATIVE_ACTIONS[group]
    recent = _RECENT_CREATIVE_CHOICES.setdefault(group, deque(maxlen=3))
    available = [i for i in range(len(options)) if i not in recent] or list(range(len(options)))
    index = random.SystemRandom().choice(available)
    recent.append(index)
    action = options[index]
    if part >= 2:
        action = (
            "CONTINUATION: " + action
            + " Match the previous clip's final frame, setting, lighting and product orientation; continue the action without repeating its hook or main gesture."
        )
    audio = _SFX_BY_TYPE[group]
    return (
        "VISUAL VARIATION: " + action + "\n"
        + "AUDIO: " + audio + " Keep music soft under speech; use only brief SFX that match visible action. If the video model cannot create audio, add voice, music and SFX in post-production.\n"
        + "QUALITY: One clear action and at most one controlled camera move per beat. Preserve product shape, colour, markings and scale; keep motion, lighting and contact realistic. Smooth continuity, no morphing, duplication, warping, flicker or unrequested on-screen text."
    )


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


def _category_specific_scenes(product_type, product):
    """Build visual beats that suit the product category without assuming unseen features."""
    words = str(product or "").casefold()
    if product_type in {"home", "furniture", "baby"} and any(
        term in words for term in ("bed", "katil", "bedframe", "bed frame", "headboard")
    ):
        return [
            ("HOOK / DISTINCTIVE SILHOUETTE", "Open on the most distinctive reference-visible part of the bed, then reveal enough of the full silhouette to identify it immediately."),
            ("FULL BED REVEAL", "Show the complete bed in a believable bedroom scale. Preserve the headboard, frame, rails, footboard, colour and proportions exactly as shown."),
            ("CONSTRUCTION DETAIL", "Make a gentle close pass across one or two genuinely visible structural details. Show a mattress, stool or other piece only if it appears in the reference or supplied product details."),
            ("ROOM CONTEXT", "Use one restrained camera move to show how the unchanged bed sits in the room; keep all parts grounded and do not demonstrate unsupported storage or functions."),
            ("CTA / HERO HOLD", "Return to a clear full-bed composition and hold it steadily, leaving uncluttered negative space; no on-screen text unless explicitly selected.")
        ]
    if product_type in {"home", "kitchen", "equipment", "gadget"} and any(
        term in words for term in ("cookware", "quickchef", "pan set", "pot set", "kitchen set", "7pcs", "7 pcs", "cookware set", "saucepan", "frying pan")
    ):
        return [
            ("HOOK / COMPLETE SET", "Open on the complete supplied set arranged clearly so the viewer can understand the set at a glance; do not add pieces."),
            ("SET OVERVIEW", "Make a smooth, short camera move across the actual items and return to a composition that shows the set together."),
            ("REALISTIC USE", "Show one simple, physically plausible kitchen action with an item and utensil that are actually included or explicitly described. Do not invent a feature, coating, capacity or performance claim."),
            ("PRACTICAL DETAIL / VALUE", "Highlight a visible handle, shape, stack or included component only where supported by the product name or reference; communicate value through the actual set contents, not invented savings."),
            ("CTA / HERO HOLD", "Finish with the complete unchanged set neatly arranged and clearly visible; leave uncluttered negative space; no on-screen text unless explicitly selected.")
        ]
    scenes_by_type = {
        "fashion": [
            ("HOOK / OUTFIT REVEAL", "Start with a striking but natural full-outfit view; keep the model and garment visible."),
            ("FULL LOOK", "Use one relaxed, realistic model movement to show the garment's actual cut, fit and overall silhouette."),
            ("FABRIC / DESIGN DETAIL", "Move closer to a genuinely visible print, seam, sleeve, hem or fabric detail; do not invent texture or alter the pattern."),
            ("NATURAL MOVEMENT", "Show one category-appropriate step, gentle turn or natural fabric movement without exaggerated posing or wind."),
            ("CTA / OUTFIT HERO", "Settle on a clean full-outfit view with the garment unchanged and uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
        "hijab": [
            ("HOOK / DRAPE REVEAL", "Open on the actual drape and overall styling, then show the full visible arrangement."),
            ("FULL STYLING", "Use a small natural head or shoulder movement while keeping the wrap and folds consistent."),
            ("FABRIC DETAIL", "Show only visible folds, edging, print or texture; do not change the wrap, colour or fabric."),
            ("NATURAL PROFILE", "Make a gentle three-quarter camera adjustment to show the existing drape from a plausible angle."),
            ("CTA / STYLING HERO", "Return to a clear, steady view of the same styling with uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
        "shoes": [
            ("HOOK / SHOE SILHOUETTE", "Open at a low three-quarter angle with the complete shoe or pair clearly visible."),
            ("ON-FOOT OR PRODUCT VIEW", "If a wearer is selected, show a short natural step on a flat surface; otherwise keep the shoes grounded and stationary."),
            ("VISIBLE DETAIL", "Highlight only the visible upper, fastening, sidewall or sole edge; never force an unseen angle."),
            ("NATURAL MOVEMENT", "Show a small, believable shift or two-step walk only if appropriate, preserving shoe shape and foot contact."),
            ("CTA / SHOE HERO", "Hold a clean view of the unchanged pair or product arrangement with uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
        "bag": [
            ("HOOK / BAG SHAPE", "Open on the bag's clearest recognizable silhouette, with all visible straps and handles in frame."),
            ("FULL PRODUCT REVEAL", "Show the complete bag at a believable scale in the selected setting; do not add contents or accessories."),
            ("HARDWARE / SEAM DETAIL", "Move close to one visible seam, handle, clasp or hardware detail only if present."),
            ("PLAUSIBLE HANDLING", "If the scene calls for it, show one natural lift or carry using an existing handle or strap; otherwise move the camera only."),
            ("CTA / BAG HERO", "Return to the same complete bag and hold a stable frame with uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
        "beauty": [
            ("HOOK / PACKAGING REVEAL", "Open with a clean, recognizable view of the actual package and keep its label and shape consistent."),
            ("PRODUCT PRESENTATION", "Show the whole product in a tidy, relevant setting; do not add extra containers or applicators."),
            ("VISIBLE DETAIL / TEXTURE", "Highlight a genuinely visible package or product texture detail without inventing ingredients, shade or efficacy."),
            ("REALISTIC USE CONTEXT", "Show only a small, plausible use action if the selected product supports it; otherwise use a restrained close-up."),
            ("CTA / PRODUCT HERO", "Finish with the original product clearly framed and uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
        "food": [
            ("HOOK / APPETIZING VIEW", "Open on the actual food or drink with natural, appetizing light; do not add toppings or ingredients."),
            ("FULL SERVING", "Show the complete original serving and packaging, where present."),
            ("TEXTURE DETAIL", "Make a gentle close-up of visible texture, crumb, surface or liquid; preserve the actual appearance."),
            ("SERVING MOMENT", "Use one plausible serving or pouring action only if supported by the product and scene; avoid exaggerated effects."),
            ("CTA / PRODUCT HERO", "Return to the real serving or package and hold a clean final composition with uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
        "gadget": [
            ("HOOK / DEVICE REVEAL", "Open on a recognizable three-quarter view of the unchanged device."),
            ("FULL DEVICE VIEW", "Show the complete device and any supplied components without adding cables or accessories."),
            ("VISIBLE CONTROL / PORT", "Move close only to a control, port, screen or button that is actually visible; keep screen content unchanged."),
            ("PLAUSIBLE DEMONSTRATION", "Show one simple action the named product genuinely supports; do not invent compatibility, specifications or functions."),
            ("CTA / DEVICE HERO", "Finish with a stable, complete device view and uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
    }
    return scenes_by_type.get(product_type, [
        ("HOOK / PRODUCT RECOGNITION", "Open with a distinctive, reference-safe view that identifies the product quickly."),
        ("FULL PRODUCT REVEAL", "Show the complete product in a believable setting and at realistic scale."),
        ("VISIBLE DETAIL", "Highlight one genuinely visible detail; do not invent materials, functions or accessories."),
        ("PLAUSIBLE USE OR PRESENTATION", "Show one natural action suited to the named product; if no action is supported, use a restrained camera move."),
        ("CTA / HERO HOLD", "Finish on a clear, stable view of the unchanged product with uncluttered negative space; no on-screen text unless explicitly selected.")
    ])


CAMERAS = {
    "orbit": "A restrained camera arc of at most 30 degrees with subtle parallax. Never reveal or fabricate an unseen side.",
    "push": "A smooth slow dolly-in from a balanced medium product shot to a crisp detail, with no digital warping.",
    "side": "A measured left-to-right lateral camera slide with gentle depth separation and stable product proportions.",
    "static": "A locked premium studio composition with delicate lighting movement and a subtle focus transition.",
}

_AUTO_STYLE_CANDIDATES = {
    # Auto selects a category-fit style and avoids repeating the last three choices.
    "fashion": ["fashion_editorial", "lifestyle", "golden_hour", "creative_reveal", "fast_cut"],
    "bag": ["handbag_showcase", "bag_daily_carry", "bag_tabletop_reveal", "sling_bag_lifestyle", "bag_detail_macro", "bag_flatlay"],
    "wallet": ["wallet_luxury_macro", "wallet_open_close", "wallet_daily_carry", "wallet_flatlay", "wallet_gift_reveal"],
    "hijab": ["fashion_editorial", "lifestyle", "golden_hour", "minimal", "creative_reveal"],
    "shoes": ["studio_360_safe", "pov_demo", "fast_cut", "lifestyle", "cinematic"],
    "beauty": ["beauty_macro", "lifestyle", "luxury", "flatlay", "creative_reveal"],
    "food": ["food_appetite", "lifestyle", "fast_cut", "cozy_home", "nature_fresh"],
    "gadget": ["tech_demo", "pov_demo", "studio_360_safe", "fast_cut", "cinematic"],
    "equipment": ["tech_demo", "studio_360_safe", "minimal", "cinematic"],
    "home": ["cozy_home", "minimal", "lifestyle", "flatlay", "cinematic"],
    "accessory": ["luxury", "creative_reveal", "studio_360_safe", "fashion_editorial", "flatlay"],
    "toy": ["playful_viral", "dynamic", "creative_reveal", "lifestyle"],
    "book_stationery": ["flatlay", "minimal", "creative_reveal", "lifestyle"],
    "sports": ["pov_demo", "dynamic", "fast_cut", "studio_360_safe"],
    "pet": ["lifestyle", "nature_fresh", "cozy_home", "cinematic", "playful_viral"],
    "automotive": ["studio_360_safe", "tech_demo", "cinematic", "luxury"],
    "baby": ["cozy_home", "lifestyle", "minimal", "flatlay"],
    "travel": ["studio_360_safe", "lifestyle", "pov_demo", "cinematic"],
    "office": ["flatlay", "tech_demo", "minimal", "cinematic"],
    "garden": ["nature_fresh", "lifestyle", "cozy_home", "cinematic"],
    "kitchen": ["cozy_home", "food_appetite", "minimal", "lifestyle"],
    "furniture": ["cozy_home", "cinematic", "minimal", "lifestyle"],
    "crafts": ["flatlay", "creative_reveal", "minimal", "lifestyle"],
    "other": ["cinematic", "minimal", "lifestyle", "creative_reveal", "flatlay", "studio_360_safe"],
}
_RECENT_AUTO_STYLES = {}


def _resolve_auto_style(style, product_type, product="", product_subtype=""):
    """Choose a varied style that fits both the category and recognizable subtype."""
    if style != "auto":
        return style
    category = str(product_type or "other").casefold()
    subtype = str(product_subtype or "").casefold()
    product_words = str(product or "").casefold()
    candidates = None
    if category == "bag":
        if subtype in {"bag_wallet", "wallet", "card_holder"} or any(
            term in product_words for term in ("wallet", "dompet", "card holder", "cardholder", "coin purse")
        ):
            category = "wallet"
        elif subtype in {"bag_backpack", "backpack", "bag_laptop"} or any(
            term in product_words for term in ("backpack", "rucksack", "beg galas", "beg sekolah", "beg laptop")
        ):
            candidates = ["backpack_demo", "bag_daily_carry", "bag_tabletop_reveal", "lifestyle", "cinematic"]
        elif subtype in {"bag_sling", "sling_bag", "bag_handbag", "handbag", "bag_tote"} or any(
            term in product_words for term in ("sling", "crossbody", "beg silang", "tote bag", "handbag", "beg tangan")
        ):
            candidates = ["sling_bag_lifestyle", "handbag_showcase", "bag_daily_carry", "bag_tabletop_reveal", "bag_flatlay"]
        else:
            candidates = _AUTO_STYLE_CANDIDATES["bag"]
    if candidates is None:
        candidates = _AUTO_STYLE_CANDIDATES.get(category, _AUTO_STYLE_CANDIDATES["other"])
    group = category + ":" + subtype if subtype else category
    recent = _RECENT_AUTO_STYLES.setdefault(group, deque(maxlen=min(3, max(1, len(candidates) - 1))))
    available = [key for key in candidates if key not in recent] or list(candidates)
    selected = random.SystemRandom().choice(available)
    recent.append(selected)
    return selected


# These directions are injected only when the user selects that ad approach.
# They shape the actual hook/story and CTA; they are not a universal paragraph.
_CREATIVE_ANGLE_INSTRUCTIONS = {
    "question": (
        "AD APPROACH — QUESTION HOOK: Open with one short, natural question tied to "
        "the product's visible design or a plausible use case. Answer it visually by "
        "showing the product and only verified details; finish with a clear, low-pressure "
        "CTA to view the product details or available options. Do not invent a problem or benefit."
    ),
    "reveal": (
        "AD APPROACH — PRODUCT REVEAL: Open on a tight but recognizable view, then reveal "
        "the complete unchanged product within the opening beat. Build interest through "
        "camera movement and reference-visible details, then close with a concise CTA to explore it."
    ),
    "demo": (
        "AD APPROACH — QUICK DEMONSTRATION: Open with the product ready for one simple, "
        "physically plausible action it genuinely supports. Show the action clearly, then "
        "close with a CTA to check product details. Never invent functions or hidden features."
    ),
    "relatable": (
        "AD APPROACH — RELATABLE MOMENT: Open with a believable everyday situation relevant "
        "to this product. Show the product naturally in that context without promising an "
        "unverified result, then finish with a conversational invitation to view the product."
    ),
    "premium": (
        "AD APPROACH — PREMIUM EDITORIAL: Open with a refined hero composition, deliberate "
        "lighting and a restrained camera move. Use purposeful close-ups of genuine visible "
        "details, then end with an understated, elegant CTA. Avoid unsupported luxury claims."
    ),
    "affiliate": (
        "AD APPROACH — LIVELY AFFILIATE: Open with an energetic, conversational Malaysian "
        "promoter hook. Keep the product clearly visible and mention only verified details; "
        "finish with a direct shopping CTA such as 'Semak produk ini sekarang'. Never invent "
        "prices, discounts, stock limits, popularity or false urgency."
    ),
}


def creative_angle_instruction(angle):
    """Return only the selected ad-angle direction; auto leaves category logic in control."""
    return _CREATIVE_ANGLE_INSTRUCTIONS.get(str(angle or "auto"), "")


def build_prompt(mode, product, scene, motion, style='auto', duration=10, concept='', product_type='other', storyboard_override=None, split=None, universal_custom=False, product_subtype='', prompt_language='Malay'):
    # Preserve the historical API behavior: a 20-second call without an explicit
    # split choice still returns two connected 10-second prompts.
    if split is None:
        split = duration in (20, 30)
    style = _resolve_auto_style(style, product_type, product, product_subtype) if mode == 'storyboard' else style
    if split and duration > 10:
        # Generate connected 10-second prompts while retaining the same style and product context.
        parts = [
            _build_single_prompt(mode, product, scene, motion, style, part=index, duration=10,
                                 concept=concept, product_type=product_type, storyboard_override=storyboard_override, universal_custom=universal_custom, prompt_language=prompt_language)
            + "\n\n" + _creative_variation(product_type, product, index, product_subtype)
            for index in range(1, duration // 10 + 1)
        ]
        return "\n\n".join(
            ("=== KLIPPO PART " + str(index + 1) + " ===\n\n" + part) if index else part
            for index, part in enumerate(parts)
        )
    return (_build_single_prompt(mode, product, scene, motion, style, part=0, duration=duration,
                                concept=concept, product_type=product_type, storyboard_override=storyboard_override, universal_custom=universal_custom, prompt_language=prompt_language)
            + "\n\n" + _creative_variation(product_type, product, 0, product_subtype))


def _build_single_prompt(mode, product, scene, motion, style='auto', part=0, duration=10, concept='', product_type='other', storyboard_override=None, universal_custom=False, prompt_language='Malay'):
    scene_text = str(scene or '').lower()
    selected_scene_lock = "LOCATION: Keep every shot in the selected setting (" + str(scene or "a realistic setting suited to the product") + "); do not substitute another location. "
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
        " PRODUCT-SPECIFIC SPOKEN COPY: If voice is selected, use a short line about this product. "
        "When Malay speech is selected, use natural Bahasa Melayu Malaysia pronunciation. "
        "Vary the hook and keep it concise. No added logos or watermarks."
    )
    concise_category_direction = {
        'fashion': "Show the selected clothing naturally; preserve its exact cut, colour and pattern.",
        'bag': "Show the selected bag naturally carried, worn or placed; preserve its visible design.",
        'wallet': "Focus on the wallet and hands; show only visible features.",
        'hijab': "Show the selected hijab's actual drape, folds, colour and pattern.",
        'shoes': "Keep the footwear clearly visible with natural, believable steps.",
        'beauty': "Focus on the packaging and visible product texture.",
        'food': "Show the actual food or drink appetizingly and realistically.",
        'gadget': "Focus on the device and visible controls; preserve its exact shape.",
        'home': "Show the product in a believable everyday setting.",
        'accessory': "Use close framing that clearly shows the selected accessory.",
        'travel': "Show the travel item handled naturally and realistically.",
        'pet': "Show the pet accessory in a calm, appropriate setting.",
        'automotive': "Show the car accessory clearly in a safe, stationary setting.",
        'garden': "Show the garden product in a realistic outdoor setting.",
        'kitchen': "Show the kitchen product in a practical, believable use.",
        'furniture': "Preserve the furniture's exact shape, proportions and visible construction.",
        'baby': "Show the baby product in a calm, age-appropriate setting.",
        'crafts': "Show the craft product with one plausible, simple action.",
        'other': "Present the product clearly without assuming unlisted features.",
    }.get(product_type, "Present the product clearly and realistically.")
    concise_category_direction += " Preserve visible product details; invent no features."
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
        concise_framework = ""
        if product_type == "other" or universal_custom:
            concise_framework = (
                " UNIVERSAL CREATIVE FRAMEWORK: " + _universal_prompt_direction(style_key)
                + " UNIVERSAL SAFETY RULES: Preserve visible product details; invent no features or claims."
            )
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
                scenes = _category_specific_scenes(product_type, product)
                clip_label = "SECOND CLIP 10s" if part == 2 else "THIRD CLIP 10s" if part == 3 else "CONTINUATION CLIP 10s"
                beat_plan = (
                    clip_label + ": 0–2s CONTINUITY BRIDGE — resume the exact previous final frame and do not repeat the hook; "
                    + "2–4s CATEGORY ACTION — " + scenes[3][1] + " "
                    + "4–6s VISIBLE DETAIL — " + scenes[2][1] + " "
                    + "6–8s NATURAL FOLLOW-THROUGH — continue the same setting and product orientation; "
                    + "8–10s HERO HOLD — finish with the complete unchanged product clearly visible. "
                    + "Do NOT repeat the opening hook or restart the reveal. "
                )
            elif not (storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4):
                scenes = _category_specific_scenes(product_type, product)
                scene_length = duration / 5
                timed_scenes = []
                for index, (shot_name, shot_direction) in enumerate(scenes):
                    start_time = index * scene_length
                    end_time = start_time + scene_length
                    if index == 4 and duration == 10 and (part == 1 or doodle):
                        shot_direction += " HOLD the final frame in a stable full-product composition for a seamless Part 2 handoff; no fade."
                    timed_scenes.append(
                        f"{start_time:g}–{end_time:g}s {shot_name}: {shot_direction}"
                    )
                timing_summary = (
                    "TIMING: 0–6s clear product reveal; 6–12s show the complete product in its setting; "
                    "12–18s highlight one genuinely visible detail; 18–24s one subtle category-appropriate action; "
                    "24–30s stable full-product hero finish. "
                    if duration == 30 else ""
                )
                beat_plan = (
                    timing_summary
                    + "CATEGORY-SPECIFIC STORYBOARD — one continuous video with five connected timed beats: "
                    + " | ".join(timed_scenes)
                    + (" Do not perform the main surrounding contour yet." if doodle and part <= 1 else "")
                )
            if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
                beat_labels = (
                    "HOOK",
                    "FUNCTION + BENEFIT",
                    "VALUE / VISIBLE DETAIL",
                    "CTA + HERO SHOT",
                )
                beat_plan = (
                    "SELECTED STORYBOARD: FOUR-BEAT STRUCTURE — exactly 0–2s HOOK, 2–6s FUNCTION + BENEFIT, "
                    "6–8s VALUE / VISIBLE DETAIL, 8–10s CTA + HERO SHOT. "
                    + (("CONTINUITY: Resume from Part 1's final frame; do not repeat its hook. ")
                       if part >= 2 else "")
                    + " | ".join(
                        beat_labels[index] + " — " + str(item.get("shot", "")) + ": "
                        + str(item.get("direction", ""))
                        for index, item in enumerate(storyboard_override)
                    ) + ". "
                )
            hook_rule = (
                "HOOK + CTA: Make the opening visually specific to this product. The middle must show a plausible use "
                "and a benefit supported by the product details; the third beat shows its value or a visible detail; "
                "the final beat is a clear CTA with a full-product hero shot. Never invent product claims. Use only supported product details. "
                + ("If voice or on-screen text is selected, use a short, natural, product-specific hook and CTA that match the selected options. "
                   if part < 2 else "Continue naturally without repeating the opening hook. ")
            )
            if doodle and duration == 10 and part == 1 and "HOLD the final frame" not in beat_plan:
                beat_plan += " HOLD the final frame in a stable full-product composition for a seamless Part 2 handoff; no fade. "
            doodle_rule = (
                "DOODLE + MATCHED SFX: Thin hand-drawn lines travel smoothly just outside the visible product outline; "
                "sync a soft pencil-draw or light whoosh to the line movement, a tiny sparkle/chime when a visible detail is highlighted, "
                "and a gentle pop only when a circle or doodle accent appears. Keep each effect brief, timed to the visual, and quieter than speech/music; "
                "do not stack effects or cover the product. If audio generation is unsupported, do not claim the SFX will be rendered. "
                if doodle else ""
            )
            concept_rule = ("CREATIVE IDEA: " + _prompt_sentence(concept, 180, "") + " " if concept and concept.strip() else "")
            return (
                "VIDEO PROMPT — " + str(duration) + " SECONDS" + (" | PART " + str(part) if part else "") + "\n"
                "Vertical 9:16, realistic product video, exactly " + str(duration) + " seconds.\n"
                + "STYLE: " + style_name + " — " + _prompt_sentence(style_template, 180, "Use a realistic product-focused presentation.") + "\n"
                + "PRODUCT: " + product + "\n" + concise_category_direction + concise_framework
                + (" UNIVERSAL SAFETY RULES: Preserve visible product details; invent no features or claims."
                   if product_type == "other" or universal_custom else "") + "\n"
                + "SETTING: " + _prompt_sentence(scene, 100, "A realistic setting suited to the product.") + " CAMERA: " + _prompt_sentence(camera, 110, "Use one restrained camera move and keep the product stable.") + "\n"
                + "PRODUCT LOCK: Preserve the reference product's visible design, colour, pattern, branding and proportions. Do not invent features or accessories.\n"
                + hook_rule + beat_plan + " " + concept_rule + " " + doodle_rule + " "
                + "Keep actions natural and the product consistent. Follow the selected text, audio and visual options. If voiceover is enabled, speak only in " + ("English" if str(prompt_language or "Malay").casefold() == "english" else "Bahasa Melayu Malaysia") + " and use a short, natural product-specific hook and CTA."
            )

        evidence_rules = (
            "Use the supplied product photo as truth. Preserve visible details and spelling; never invent features, materials, accessories or claims."
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
                "Part 2: resume from Part 1's exact frame, show another visible detail, continue the same concept and end on a clear hero shot. No repeated hook."
            )
        else:
            rules = (
                "Part 1: reveal the product, highlight one visible detail and hold a clear full-product frame to connect with Part 2."
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
            if part >= 2:
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
        if part == 0 and duration in (10, 20, 30):
            scene_length = duration / 5
            generic_scenes = _category_specific_scenes(product_type, product)
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
                "Preserve exact product identity, packaging, colour, scale and coherent lighting.\n\n"
                + "\n\n".join(blocks)
                + "\n\nKeep transitions natural, camera movement restrained and product geometry stable throughout."
            )
            if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
                curated_direction = storyboard_text
            else:
                rules = storyboard_text
        return (
            "VIDEO PROMPT — " + str(duration) + " SECONDS" + (" | PART " + str(part) if part else "") + "\n"
            "Realistic vertical 9:16 product ad, exactly " + str(duration) + " seconds.\n"
            "PRODUCT: " + product + "\n" + category_direction + "\n"
            + "STYLE: " + style_name + " — " + _prompt_sentence(style_template, 180, "Use a realistic product-focused presentation.") + "\n"
            + "SETTING: " + _prompt_sentence(scene, 140, "A realistic setting suited to the product.") + "\nCAMERA: " + _prompt_sentence(camera, 140, "Use one restrained camera move and keep the product stable.") + "\n"
            + (curated_direction if curated_direction else
               ((hook_direction if part != 2 else "Continue seamlessly from Part 1; do not repeat the hook.") + "\n" + rules))
            + (("\nCREATIVE IDEA: " + _prompt_sentence(concept, 180, "")) if concept else "")
            + "\nNatural movement. If voice is selected, use a short product-specific hook and CTA in " + ("English" if str(prompt_language or "Malay").casefold() == "english" else "Bahasa Melayu Malaysia") + ". No added on-screen text or watermark."
        )
    if mode == "storyboard":
        shots = [
            ("HOOK 0–2s", "Quick visual reveal; no text."),
            ("REVEAL 2–4s", "Show the whole product accurately."),
            ("CONTEXT 4–6s", "Place it in a believable setting."),
            ("DETAIL 6–8s", "Highlight one visible detail."),
            ("CLOSING 8–10s", "Hold a clean full-product shot.")
        ]
        direction = ("Five connected 2-second scenes: "
                      + " | ".join(title + ": " + detail for title, detail in shots)
                      + " Keep product identity, colour and lighting consistent. No invented features or text.")
    else:
        direction = (
            "One continuous " + str(duration) + "-second product ad. Start with a clear reveal, move gently to show one visible detail, "
            "then return to a stable full-product closing shot. Use one smooth camera move, natural light and a consistent setting. "
            "Preserve the product exactly; no invented angles, features or text."
        )
    if duration == 20:
        direction = (
            "20s: 0–4s reveal product; 4–8s gentle camera move; 8–12s show one visible detail; "
            "12–16s return to full view; 16–20s steady hero finish. One continuous scene, no invented features or text."
        )
    if part == 1:
        direction = "PART 1: reveal product, show one detail, then hold the full-product frame for Part 2."
    elif part >= 2:
        previous_part = part - 1
        direction = ("PART " + str(part) + ": match Part " + str(previous_part) + "'s final frame exactly, continue with a complementary action, "
                     "show another visible detail and end on a clear hero shot. No repeated hook or restart.")
    product_words = (product or "").lower()
    fashion_terms = ("kurung", "baju", "tudung", "hijab", "dress", "clothing", "apparel",
                     "fashion", "outfit", "blouse", "skirt", "trousers", "pants", "garment",
                     "woman wearing", "model wearing", "pakaian", "kebaya", "jubah", "abaya")
    is_fashion = any(term in product_words for term in fashion_terms)
    if is_fashion and mode != "storyboard" and part == 0 and duration != 20:
        direction = (
            "Fashion ad, one continuous shot. Show the full outfit in the selected location; use one relaxed, natural action, "
            "then a brief close view of visible fabric/design details and a steady finish. External camera, not a selfie. "
            "Keep model, clothing, colours, fit and accessories unchanged. No dancing, scene changes or invented details. "
            + selected_scene_lock
        )
    spoken_language = "English" if str(prompt_language or "Malay").casefold() == "english" else "Bahasa Melayu Malaysia"
    return (
        "VIDEO PROMPT — " + str(duration) + " SECONDS" + (" | PART " + str(part) if part else "") + "\n"
        "Realistic vertical 9:16 product ad, exactly " + str(duration) + " seconds.\n"
        "PRODUCT: " + product + "\n"
        "STYLE: " + _prompt_sentence(art, 180, "Use a realistic product-focused presentation.") + "\n"
        "SETTING: " + _prompt_sentence(scene, 140, "A realistic setting suited to the product.") + "\n"
        + direction + "\n"
        + "Preserve the product's visible design and packaging; invent no features. "
        "Natural movement, clean transitions, no added on-screen text or watermark. "
        "If voice is selected, use a short product-specific hook and CTA in " + spoken_language + "."
    )