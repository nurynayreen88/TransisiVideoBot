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


def _prompt_text(value, fallback=""):
    """Normalize whitespace without discarding user or style constraints."""
    text = " ".join(str(value or "").split()).strip()
    return text or fallback


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
    "equipment": [
        "Begin with the complete tool or appliance grounded in frame, then move closer to one visible control or working part.",
        "Show one safe, simple handling action only when the product supports it; otherwise use a restrained camera slide.",
        "Keep the equipment stationary while the camera reveals a visible connector, handle or structural detail."
    ],
    "accessory": [
        "Start with the whole accessory visible, then make a gentle close pass over one actual clasp, dial, fastening or edge.",
        "Show the item at believable scale in a hand or on a wearer only if a model is selected; otherwise use a clean tabletop reveal.",
        "Return to the full accessory after one detail shot; do not add matching items or invented attachments."
    ],
    "toy": [
        "Show the complete toy or game set first, then one simple safe interaction with an existing piece.",
        "Keep every visible piece consistent and grounded; do not add characters, accessories or effects that are not shown.",
        "Use a gentle camera move across the actual set and finish with all supplied pieces visible."
    ],
    "stationery": [
        "Begin with the full book or stationery item visible, then move to one real cover, page or writing detail.",
        "Show a page turn or pen movement only when it suits the item; do not fabricate readable text.",
        "Finish with the complete original item neatly arranged, without adding supplies."
    ],
    "sports": [
        "Start with the complete sports item grounded in frame, then show one visible grip, seam or fastening detail.",
        "Use one controlled, safe demonstration only when the product supports it; no stunts or exaggerated performance.",
        "Return to a stable full-product view after the action and keep all equipment unchanged."
    ],
    "automotive": [
        "Show the complete automotive accessory by itself first; do not invent a vehicle installation.",
        "Move close to a visible connector, mount or edge only when present in the reference.",
        "Use a stationary vehicle context only when appropriate; keep the product grounded and avoid compatibility claims."
    ],
    "baby": [
        "Keep the baby product as the hero, using a clean stable presentation and no infant unless explicitly selected and safe.",
        "Show one visible closure, support or construction detail without making safety or health claims.",
        "Use calm adult-caretaker handling only when appropriate; otherwise keep the product alone and stationary."
    ],
    "travel": [
        "Open on the complete luggage or travel item with visible handles, straps and wheels in frame.",
        "Show one natural lift, roll or carry only when supported by the product and setting.",
        "Highlight a visible zip, handle or wheel and finish with the whole unchanged item."
    ],
    "office": [
        "Show the complete office product on a tidy desk, then one simple practical interaction if supported.",
        "Move close to a visible control, edge or compartment without inventing specifications.",
        "Finish on a clean full-product view and avoid adding stationery or accessories."
    ],
    "crafts": [
        "Show the complete craft item or kit and all visible supplied pieces before any interaction.",
        "Demonstrate one safe, plausible craft action only when the actual kit supports it.",
        "Return to the original item or kit; do not invent tools, materials or a finished result."
    ],
    "garden": [
        "Open on the complete garden product at realistic scale, then show one visible construction detail.",
        "Use one safe outdoor interaction only when the product supports it; do not invent results or accessories.",
        "Finish with the full item grounded and clearly visible."
    ],
    "kitchen": [
        "Show the complete kitchen product or set before a close-up, with no extra cookware or utensils.",
        "Use one simple, physically plausible kitchen action only when supported by the product.",
        "Highlight a visible handle, lid or control and finish on the complete unchanged product."
    ],
    "general": [
        "Start with a clean wide hero composition, then use a gentle lateral slide to reveal a visible detail.",
        "Begin with a close view of a reference-visible feature, then pull back to show the complete product.",
        "Use a restrained three-quarter camera approach and settle into a clear, stable hero frame.",
        "Begin with the product already in the scene; let natural light shift subtly while the camera moves sideways."
    ]
}
# Ten safe presentation treatments are available to every product subcategory.
# These vary framing, camera language and lighting without inventing product facts.
_CREATIVE_PRESENTATION_VARIATIONS = [
    "PRESENTATION: Start in a wide three-quarter composition, then use a slow, stable push-in under soft side lighting.",
    "PRESENTATION: Use an eye-level lateral camera slide with balanced negative space and natural, consistent shadows.",
    "PRESENTATION: Begin with a close crop of a genuinely visible detail, then pull back to reveal the complete unchanged product.",
    "PRESENTATION: Keep the product grounded and use a restrained focus pull from the background to the product; do not alter any labels.",
    "PRESENTATION: Use a low three-quarter framing where suitable, then settle into a level full-product hero view without revealing unseen surfaces.",
    "PRESENTATION: Use a locked camera and a subtle, physically plausible light shift; keep colour, texture and reflections true to the reference.",
    "PRESENTATION: Start slightly off-centre and make one smooth reframing move into a balanced composition; preserve the product's orientation.",
    "PRESENTATION: Use a gentle overhead or high-angle view only when the product can be shown clearly from that angle; do not expose unseen details.",
    "PRESENTATION: Use two clean match-cut framings at most, keeping product scale, position, lighting and geometry consistent across the cuts.",
    "PRESENTATION: Begin with a contextual medium-wide shot, then make one controlled camera move toward the hero product while keeping it fully recognizable."
]

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
    "equipment": "Use a restrained mechanical click or soft switch sound only if a visible control is used; no invented machine noise.",
    "accessory": "Use a tiny, natural fastening or handling sound only if the action is visible; otherwise keep music understated.",
    "toy": "Use a soft, brief movement sound only when the toy visibly moves; avoid cartoon effects or extra voices.",
    "stationery": "Use a quiet page turn, paper movement or pen sound only when visible; keep it subtle.",
    "sports": "Use a natural contact sound only when the visible action supports it; no exaggerated impacts.",
    "automotive": "Use a restrained fitting or handling sound only if shown; do not add engine sounds to a product-only shot.",
    "baby": "Use gentle, calm room tone and a soft placement sound only if visible; no crying or invented baby sounds.",
    "travel": "Use a quiet wheel roll, zip or handle movement only if visible; no airport ambience unless the setting is selected.",
    "office": "Use a subtle paper, keyboard or placement sound only if the corresponding action is visible.",
    "crafts": "Use a light tool or material sound only if visible and plausible; no extra tools.",
    "garden": "Use gentle outdoor ambience only if the setting is outdoors; match handling sounds to visible action.",
    "kitchen": "Use a light utensil or placement sound only if visible; no exaggerated sizzling or invented cooking sounds.",
    "general": "Use one subtle soft chime, tiny pop or gentle whoosh at a matching visual beat; never stack effects."
}


# Load the additive per-subcategory variation library. The master prompt library stays untouched.
_SUBCATEGORY_VARIATION_PATH = Path(__file__).resolve().parent / "prompts" / "subcategory_variation_library.json"
try:
    with _SUBCATEGORY_VARIATION_PATH.open("r", encoding="utf-8") as _variation_handle:
        _subcategory_variation_data = json.load(_variation_handle)
    _SUBCATEGORY_VARIATIONS_BY_ID = {
        str(item.get("subcategory_id")): list(item.get("variations", []))
        for item in _subcategory_variation_data.get("subcategories", [])
        if isinstance(item, dict) and item.get("subcategory_id")
    }
    # Load split additions without replacing or deleting the master catalog.
    _variation_ids = {
        str(v.get("id")) for values in _SUBCATEGORY_VARIATIONS_BY_ID.values()
        for v in values if isinstance(v, dict)
    }
    _batch_dir = _SUBCATEGORY_VARIATION_PATH.parent / "staging_batch100_20261023"
    for _batch_path in sorted(_batch_dir.glob("part_*.json")):
        try:
            with _batch_path.open("r", encoding="utf-8") as _batch_handle:
                _batch = json.load(_batch_handle)
            _entries = _batch.get("variations", [])
            if not isinstance(_entries, list) or len(_entries) != _batch.get("variation_count"):
                continue
            for _entry in _entries:
                if not isinstance(_entry, dict):
                    continue
                _entry_id = str(_entry.get("id", ""))
                _subcategory_id, _sep, _number = _entry_id.rpartition("_v")
                if (not _sep or not _number.isdigit() or
                        _entry.get("variation_number") != int(_number) or
                        _entry_id in _variation_ids or
                        _subcategory_id not in _SUBCATEGORY_VARIATIONS_BY_ID):
                    continue
                if any(not _entry.get(field) for field in
                       ("name", "hook", "action", "detail", "camera", "lighting", "closing", "audio")):
                    continue
                _SUBCATEGORY_VARIATIONS_BY_ID[_subcategory_id].append(_entry)
                _variation_ids.add(_entry_id)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
except (OSError, json.JSONDecodeError):
    _SUBCATEGORY_VARIATIONS_BY_ID = {}

_RECENT_SUBCATEGORY_VARIATIONS = {}


def _creative_variation(product_type, product, part, product_subtype=''):
    """Select a safe, varied creative direction, preferring the exact selected subcategory."""
    words = " ".join(str(value or "") for value in (product_type, product_subtype, product)).casefold()
    type_key = str(product_type or "").casefold()
    subtype_key = str(product_subtype or "").casefold()
    if type_key in {"fashion", "hijab"} or (type_key == "other" and not subtype_key and any(w in words for w in ("dress", "clothing", "fashion", "apparel", "outfit", "garment", "pakaian", "baju", "skirt", "shirt", "t-shirt", "hijab", "tudung", "blouse"))):
        group = "fashion"
    elif type_key == "wallet" or (type_key == "bag" and (subtype_key in {"bag_wallet", "wallet", "card_holder"} or (not subtype_key and any(w in words for w in ("wallet", "dompet", "card holder", "cardholder", "coin purse"))))):
        group = "wallet"
    elif type_key == "travel":
        group = "travel"
    elif type_key == "bag" or any(w in words for w in ("bag", "handbag", "backpack", "purse", "beg galas", "beg tangan")):
        group = "bag"
    elif type_key == "shoes" or any(w in words for w in ("shoe", "sneaker", "sandal", "footwear", "kasut", "selipar")):
        group = "shoes"
    elif type_key == "pet" or any(w in words for w in ("pet", "kucing", "anjing", "arnab", "rabbit", "hamster", "bird cage", "fish tank", "haiwan")):
        group = "pet"
    elif type_key == "beauty" or any(w in words for w in ("beauty", "cosmetic", "skincare", "perfume", "lipstick", "makeup", "serum")):
        group = "beauty"
    elif type_key == "food" or any(w in words for w in ("food", "drink", "snack", "cake", "coffee", "tea", "makanan", "minuman")):
        group = "food"
    elif type_key == "gadget":
        group = "gadget"
    elif type_key == "equipment":
        group = "equipment"
    elif type_key == "accessory":
        group = "accessory"
    elif type_key == "toy":
        group = "toy"
    elif type_key == "book_stationery":
        group = "stationery"
    elif type_key == "sports":
        group = "sports"
    elif type_key == "automotive":
        group = "automotive"
    elif type_key == "baby":
        group = "baby"
    elif type_key == "office":
        group = "office"
    elif type_key == "crafts":
        group = "crafts"
    elif type_key == "garden":
        group = "garden"
    elif type_key == "kitchen":
        group = "kitchen"
    elif type_key in {"home", "furniture"}:
        group = "home"
    else:
        group = "general"

    selected_action = None
    subtype_variations = _SUBCATEGORY_VARIATIONS_BY_ID.get(subtype_key, [])
    if subtype_variations:
        recent = _RECENT_SUBCATEGORY_VARIATIONS.setdefault(subtype_key, deque(maxlen=3))
        available = [i for i in range(len(subtype_variations)) if i not in recent]
        if not available:
            available = list(range(len(subtype_variations)))
        index = random.SystemRandom().choice(available)
        recent.append(index)
        selected_action = subtype_variations[index]
        if part >= 2:
            hook = "HOOK: Resume from the previous clip's exact final frame; do not repeat its opening hook."
        else:
            hook = str(selected_action.get("hook", "")).strip()
        action = "\\n".join(
            line for line in (
                "SUBCATEGORY VARIATION: " + str(selected_action.get("name", "Product showcase")),
                hook,
                str(selected_action.get("action", "")).strip(),
                str(selected_action.get("detail", "")).strip(),
                "PRESENTATION: " + str(selected_action.get("camera", "")).strip() + " " + str(selected_action.get("lighting", "")).strip(),
                str(selected_action.get("closing", "")).strip(),
            ) if line and not line.endswith(":")
        )
        if part >= 2:
            action += " CONTINUITY: Match the previous clip's final frame, setting, lighting and product orientation; continue naturally without repeating its main gesture."
        # Curated variation audio is authoritative; do not append category SFX.
        # Unconditional appending duplicated effects and could contradict a quiet scene.
        audio = str(selected_action.get("audio", "")).strip()
        # Library entries may already include their field label; the renderer
        # adds AUDIO: below, so strip it here to avoid duplicated labels.
        audio = re.sub(r"^AUDIO:\s*", "", audio, flags=re.IGNORECASE)
        if not audio:
            audio = _SFX_BY_TYPE[group]
    else:
        options = _CREATIVE_ACTIONS[group]
        recent = _RECENT_CREATIVE_CHOICES.setdefault(group, deque(maxlen=3))
        available = [i for i in range(len(options)) if i not in recent] or list(range(len(options)))
        index = random.SystemRandom().choice(available)
        recent.append(index)
        action = options[index]
        presentation = random.SystemRandom().choice(_CREATIVE_PRESENTATION_VARIATIONS)
        action = action + "\\n" + presentation
        if part >= 2:
            action = (
                "CONTINUATION: " + action
                + " Match the previous clip's final frame, setting, lighting and product orientation; continue the action without repeating its hook or main gesture."
            )
        audio = _SFX_BY_TYPE[group]

    return (
        "VISUAL VARIATION: " + action + "\\n"
        + "AUDIO: " + audio + " Keep background music below any selected speech; use only brief SFX that match visible action. If the video model cannot create audio, add only the audio elements selected by the user in post-production.\\n"
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


# Product-use audit: practical actions by product category. These are guidance only;
# they must never override the uploaded reference or invent product capabilities.
_PRODUCT_USAGE_SCENES = {
    "fashion": ("NATURAL WEAR DEMO", "Show the model wearing the exact garment and taking one or two natural steps or a gentle turn so its actual fit and drape are visible."),
    "hijab": ("WEARING DEMO", "Show a small natural head or shoulder movement that demonstrates the existing drape; do not re-wrap or change the styling."),
    "shoes": ("ON-FOOT DEMO", "Show the shoes being worn for two natural steps on a safe, level surface, with believable foot contact and unchanged shoe design."),
    "bag": ("CARRYING DEMO", "Show one natural lift and carry using only an existing visible handle or strap; do not open unseen compartments or add contents."),
    "wallet": ("HANDLING DEMO", "Show a natural pick-up and, only if its opening is visible, a brief open-close action; do not invent card slots or capacity."),
    "accessory": ("WEAR / HANDLING DEMO", "Show one natural wear or handling action only if the item and reference support it; do not add matching accessories."),
    "furniture": ("PRACTICAL FURNITURE USE", "Show a person naturally interacting with the furniture in its intended ordinary way, only when the visible design supports it; preserve room layout and do not invent storage or mechanisms."),
    "book_stationery": ("WORKING DEMO", "Show the item performing its ordinary function, such as a page turn or a short pen mark, only when suitable; do not fabricate readable text."),
    "beauty": ("USE DEMO", "Show one small, hygienic application or dispensing action only if the product type and visible packaging support it; otherwise demonstrate handling and packaging clearly."),
    "food": ("SERVING / POURING DEMO", "Show one plausible serving, opening or pouring action only when the product format supports it; preserve the actual food and package."),
    "gadget": ("FUNCTION DEMO", "Show one simple operation using a visible control or port only when the named product clearly supports it; keep screen content and connections truthful."),
    "equipment": ("OPERATION DEMO", "Show one safe, simple operation appropriate to the named tool or appliance; keep hands clear of hazardous moving parts and invent no performance results."),
    "home": ("PRACTICAL USE", "Show one ordinary, physically plausible interaction that demonstrates the product's evident purpose; if its function is unclear, show safe placement or handling without inventing a function."),
    "kitchen": ("KITCHEN USE", "Show the product performing one plausible kitchen task, with realistic hand contact and scale; do not imply unverified heating, coating or compatibility features."),
    "pet": ("SAFE PET INTERACTION", "Show a calm, species-appropriate interaction with the product only when safe and obvious; do not force a trick or show unsafe use."),
    "toy": ("PLAY DEMO", "Show one simple, safe interaction with an existing supplied toy piece; keep every piece consistent and do not add pieces."),
    "stationery": ("WORKING DEMO", "Show the item performing its ordinary function, such as a pen making a short mark or a page being turned, only when suitable; do not fabricate readable text."),
    "sports": ("PRACTICAL DEMO", "Show one controlled, safe use of the sports item at realistic intensity; no stunts or unsupported performance claims."),
    "automotive": ("FIT / HANDLING DEMO", "Show installation or operation only if the reference and product identity clearly support it; otherwise demonstrate a visible connector or safe handling without compatibility claims."),
    "baby": ("CAREGIVER DEMO", "Show calm adult handling only where appropriate and safe; do not place a baby in a product or imply safety certification or medical benefit."),
    "travel": ("TRAVEL USE DEMO", "Show one natural carry, roll, or zip action only when the product visibly supports it; preserve existing handles, straps and wheels."),
    "office": ("WORK USE DEMO", "Show the product doing one ordinary desk task when supported, without adding unprovided accessories or fabricated screen/text content."),
    "crafts": ("CRAFT USE DEMO", "Show one safe, plausible craft action using only tools or materials actually supplied or clearly ordinary to the task; do not invent kit contents."),
    "garden": ("GARDEN USE DEMO", "Show one safe outdoor use suited to the product's evident purpose; do not invent attachments, results or environmental claims.")
}


def _category_specific_scenes(product_type, product, product_subtype=""):
    """Build visual beats that suit the product category without assuming unseen features."""
    words = str(product or "").casefold()
    subtype = str(product_subtype or "").casefold()
    cookware_terms = (
        "periuk", "kuali", "wok", "saucepan", "stockpot", "frying pan", "cooking pot",
        "cookware", "pot set", "pan set", "periuk nasi", "periuk tekanan", "dutch oven"
    )
    if any(term in words for term in cookware_terms):
        return [
            ("COMPLETE SET / COOKING CONTEXT", "Show the complete supplied cookware set if the reference depicts a set, without adding pieces; for a single pot or pan show only that product on a suitable kitchen hob at realistic scale. Keep shape, colour, handles and lid unchanged."),
            ("PREPARE TO COOK", "If a human model is selected, show that person placing plausible food into the pot or pan using ordinary ingredients and a suitable utensil; otherwise show the cookware in a credible cooking context without introducing a person. Do not present utensils or ingredients as included accessories."),
            ("ACTIVE COOKING DEMONSTRATION", "Clearly show the pot or pan being used: if a model is selected, their hand stirs or turns the food naturally while the cookware remains stable on the hob; do not invent a human model when none was selected. Use believable contact, heat and steam only where physically plausible."),
            ("FUNCTION IN CONTEXT", "Continue the same cooking action or lift the existing lid naturally only if the reference product has one. Keep the cookware visible; do not claim non-stick, material, capacity or compatibility properties."),
            ("FOOD + PRODUCT FINISH", "Show the food in the same pot or pan, then settle on a clear view of the complete unchanged product in use. No invented accessories, product claims or on-screen text.")
        ]
    if product_type == "bag" and subtype in {"bag_handbag", "handbag"}:
        return [
            ("HANDBAG REVEAL", "Show the full handbag and its visible handles."),
            ("FULL VIEW", "Show the same handbag at realistic scale."),
            ("DETAIL", "Highlight one visible design detail."),
            ("HANDLING", "Use one natural hold or placement."),
            ("HERO", "Hold a full view of the unchanged handbag.")
        ]
    if product_type == "bag" and (
        subtype in {"bag_wallet", "wallet", "card_holder"}
        or (not subtype and any(term in words for term in ("wallet", "dompet", "card holder", "cardholder", "coin purse")))
    ):
        return [
            ("HOOK / WALLET SILHOUETTE", "Open on the wallet or card holder itself, with its complete outline visible; do not frame it as a handbag."),
            ("FULL WALLET REVEAL", "Show the exact wallet shape and exterior at realistic scale; do not invent slots, pockets, capacity or materials."),
            ("VISIBLE EDGE / CLOSURE DETAIL", "Highlight only a visible seam, edge, clasp or closure if present."),
            ("PLAUSIBLE WALLET ACTION", "Open or close the wallet only if its opening is visible and the action is supported; otherwise use a gentle camera move."),
            ("CTA / WALLET HERO", "Return to a clean full-wallet view and hold steady; no straps, handbag handles or invented accessories.")
        ]
    if product_type == "bag" and (
        subtype in {"bag_backpack", "bag_laptop", "backpack"}
        or (not subtype and any(term in words for term in ("backpack", "rucksack", "beg galas", "beg sekolah", "beg laptop")))
    ):
        return [
            ("HOOK / BACKPACK SILHOUETTE", "Open on the complete backpack with its visible shoulder straps and body clearly framed."),
            ("FULL BACKPACK REVEAL", "Show the backpack upright at believable scale; do not invent compartments, laptop sleeves or included accessories."),
            ("VISIBLE STRAP / ZIP DETAIL", "Highlight only a visible strap, zip, handle or seam if present."),
            ("PLAUSIBLE BACKPACK HANDLING", "Show one natural lift or carry using existing straps; if the scene does not support it, move the camera only."),
            ("CTA / BACKPACK HERO", "Finish on the complete unchanged backpack with straps visible and no invented pockets or capacity claims.")
        ]
    if product_type in {"home", "furniture", "baby"} and (not subtype or subtype in {"home_furniture", "baby_sleep"}) and any(
        term in words for term in ("bed", "katil", "bedframe", "bed frame", "headboard")
    ):
        return [
            ("HOOK / DISTINCTIVE SILHOUETTE", "Open on the most distinctive reference-visible part of the bed, then reveal enough of the full silhouette to identify it immediately."),
            ("FULL BED REVEAL", "Show the complete bed in a believable bedroom scale. Preserve the headboard, frame, rails, footboard, colour and proportions exactly as shown."),
            ("CONSTRUCTION DETAIL", "Make a gentle close pass across one or two genuinely visible structural details. Show a mattress, stool or other piece only if it appears in the reference or supplied product details."),
            ("ROOM CONTEXT", "Use one restrained camera move to show how the unchanged bed sits in the room; keep all parts grounded and do not demonstrate unsupported storage or functions."),
            ("CTA / HERO HOLD", "Return to a clear full-bed composition and hold it steadily, leaving uncluttered negative space; no on-screen text unless explicitly selected.")
        ]
    if product_type in {"home", "kitchen", "equipment", "gadget"} and (not subtype or subtype in {"home_kitchen"}) and any(
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
        "equipment": [
            ("HOOK / EQUIPMENT REVEAL", "Open with the complete appliance, tool or equipment clearly visible and grounded."),
            ("FULL EQUIPMENT VIEW", "Show the whole product and only the components visible in the reference."),
            ("CONTROL / BUILD DETAIL", "Highlight a visible switch, connector, handle or construction detail; do not invent specifications."),
            ("PLAUSIBLE OPERATION", "Show one safe, simple action only when the named product clearly supports it; never imply a performance result."),
            ("CTA / EQUIPMENT HERO", "Return to a stable full-product view with all parts visible; no on-screen text unless explicitly selected.")
        ],
        "home": [
            ("HOOK / HOME PRODUCT REVEAL", "Open with the complete product in a believable home setting at realistic scale."),
            ("FULL PRODUCT VIEW", "Show the item's overall shape and placement without adding unconfirmed decor or included accessories."),
            ("VISIBLE DESIGN DETAIL", "Highlight one visible finish, edge, texture or functional part without naming unsupported materials."),
            ("NATURAL HOME CONTEXT", "Use a subtle camera move or one plausible interaction; do not demonstrate an unverified function."),
            ("CTA / HOME HERO", "Finish with the complete unchanged product clearly framed and uncluttered; no on-screen text unless explicitly selected.")
        ],
        "accessory": [
            ("HOOK / ACCESSORY REVEAL", "Open on the accessory's most recognizable visible shape, with the full item in frame."),
            ("FULL ACCESSORY VIEW", "Keep the complete item and any visible fastening or strap clear; do not add matching accessories."),
            ("VISIBLE FINISH DETAIL", "Move close to one visible clasp, dial, setting, edge or surface detail only if present."),
            ("NATURAL SCALE / HANDLING", "Show the item at believable scale, using a hand or wearer only if selected and appropriate."),
            ("CTA / ACCESSORY HERO", "Return to a clear full-item view and hold steady; no on-screen text unless explicitly selected.")
        ],
        "toy": [
            ("HOOK / TOY REVEAL", "Open with the complete toy or game set arranged so its actual contents are immediately clear."),
            ("FULL SET VIEW", "Show only pieces visible in the reference; do not duplicate, add or remove components."),
            ("DETAIL / MECHANISM", "Highlight a visible piece, texture or mechanism without inventing lights, sounds or functions."),
            ("PLAUSIBLE PLAY ACTION", "Show one simple, safe interaction consistent with the toy; use a child only when a child model is explicitly selected."),
            ("CTA / TOY HERO", "Finish with the complete unchanged toy or set neatly visible; no on-screen text unless explicitly selected.")
        ],
        "book_stationery": [
            ("HOOK / STATIONERY REVEAL", "Open on the full book, notebook or stationery item with its cover and shape readable."),
            ("FULL ITEM VIEW", "Keep the complete item and any supplied pieces visible without adding stationery."),
            ("PRINT / PAPER DETAIL", "Show only readable text and printed details actually present in the reference; do not fabricate page content."),
            ("NATURAL DESK ACTION", "Use a gentle page turn or writing gesture only if it suits the product and does not alter visible text."),
            ("CTA / STATIONERY HERO", "Finish with a clear view of the original item and uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
        "sports": [
            ("HOOK / SPORTS GEAR REVEAL", "Open on the complete sports item or equipment in a stable, recognizable composition."),
            ("FULL GEAR VIEW", "Show the whole item at realistic scale with no extra accessories or invented parts."),
            ("VISIBLE MATERIAL / GRIP DETAIL", "Highlight a visible seam, grip, fastener or surface detail without claiming performance."),
            ("SAFE PRACTICAL ACTION", "Show one simple, controlled use only when appropriate for the item; no risky stunts or exaggerated results."),
            ("CTA / SPORTS HERO", "Return to a stable full-product view with the item unchanged; no on-screen text unless explicitly selected.")
        ],
        "pet": [
            ("HOOK / PET PRODUCT REVEAL", "Open on the complete pet product, clearly showing its actual shape and supplied parts."),
            ("FULL PRODUCT VIEW", "Keep the product grounded and at realistic scale; do not add food, toys or accessories."),
            ("VISIBLE DETAIL", "Highlight one genuinely visible fastening, bowl, texture or structural detail."),
            ("CALM PET CONTEXT", "If an animal model is selected, show calm, species-appropriate interaction only when safe; otherwise use a product-only camera move."),
            ("CTA / PET PRODUCT HERO", "Finish with the complete unchanged product clearly visible; no on-screen text unless explicitly selected.")
        ],
        "automotive": [
            ("HOOK / AUTOMOTIVE ITEM REVEAL", "Open on the exact automotive product or accessory, not an invented vehicle or installation."),
            ("FULL ITEM VIEW", "Show the whole supplied item and its visible connectors or mounting parts."),
            ("FIT / CONNECTOR DETAIL", "Highlight a visible connector, edge, fastening or control without claiming compatibility."),
            ("PLAUSIBLE CONTEXT", "Use a simple, stationary vehicle context only when relevant and supported; do not fabricate fitment or operation."),
            ("CTA / AUTOMOTIVE HERO", "Return to a clean full-item view with all parts unchanged; no on-screen text unless explicitly selected.")
        ],
        "baby": [
            ("HOOK / BABY PRODUCT REVEAL", "Open on the complete baby product in a clean, calm setting; do not add a baby or caregiver unless selected."),
            ("FULL PRODUCT VIEW", "Show the item's true size, shape and included components without adding accessories."),
            ("VISIBLE SAFETY / DESIGN DETAIL", "Highlight only visible construction, closure or support details; do not make safety or health claims."),
            ("GENTLE CONTEXT", "Use calm, safe handling only when the product and selected model support it; never show unsafe infant positioning."),
            ("CTA / BABY PRODUCT HERO", "Finish with the complete unchanged item clearly visible; no on-screen text unless explicitly selected.")
        ],
        "travel": [
            ("HOOK / TRAVEL ITEM REVEAL", "Open with the complete travel item, including all visible handles, straps and wheels."),
            ("FULL ITEM VIEW", "Show the item at realistic scale and preserve its exact shape and included parts."),
            ("VISIBLE TRAVEL DETAIL", "Highlight a visible zip, handle, wheel or fastening without inventing capacity or security features."),
            ("NATURAL HANDLING", "Show one simple lift, roll or carry only when the item supports it and the selected setting makes sense."),
            ("CTA / TRAVEL HERO", "Return to a clear full-item view and hold steady; no on-screen text unless explicitly selected.")
        ],
        "office": [
            ("HOOK / OFFICE PRODUCT REVEAL", "Open on the complete office item in a tidy, believable workspace."),
            ("FULL ITEM VIEW", "Show the whole product and only the components supplied or visible."),
            ("VISIBLE FUNCTIONAL DETAIL", "Highlight a real button, edge, compartment or surface detail without inventing specifications."),
            ("PRACTICAL DESK ACTION", "Show one simple, plausible desk-use action only when supported by the product."),
            ("CTA / OFFICE HERO", "Finish with a stable full-product composition and uncluttered negative space; no on-screen text unless explicitly selected.")
        ],
        "kitchen": [
            ("HOOK / KITCHEN PRODUCT REVEAL", "Open on the complete kitchen item or set, showing all supplied pieces."),
            ("FULL PRODUCT VIEW", "Keep the product grounded and show only confirmed components."),
            ("VISIBLE COOKING DETAIL", "Highlight a visible handle, lid, control or included utensil without inventing coating or capacity."),
            ("PLAUSIBLE KITCHEN ACTION", "Show one simple, physically plausible action only if supported by the product; do not imply a result."),
            ("CTA / KITCHEN HERO", "Finish with the complete unchanged product clearly visible; no on-screen text unless explicitly selected.")
        ],
        "furniture": [
            ("HOOK / FURNITURE SILHOUETTE", "Open with the full furniture piece at believable room scale."),
            ("FULL FURNITURE VIEW", "Show the complete item and preserve its visible structure, colour and proportions."),
            ("VISIBLE CONSTRUCTION DETAIL", "Highlight only a visible joint, edge, handle or surface feature."),
            ("ROOM CONTEXT", "Use one gentle camera move to show placement; do not demonstrate storage, folding or other functions unless visible and supported."),
            ("CTA / FURNITURE HERO", "Return to the full item in a stable, uncluttered composition; no on-screen text unless explicitly selected.")
        ],
        "garden": [
            ("HOOK / GARDEN PRODUCT REVEAL", "Open on the complete garden item with its visible shape and parts clear."),
            ("FULL ITEM VIEW", "Show the product at realistic scale without adding plants, tools or accessories not supplied."),
            ("VISIBLE BUILD DETAIL", "Highlight one visible connector, edge, nozzle or surface feature."),
            ("PLAUSIBLE OUTDOOR USE", "Show one simple, safe use only when the product clearly supports it; do not invent results."),
            ("CTA / GARDEN HERO", "Finish on the unchanged full product in a clean outdoor or neutral setting; no on-screen text unless explicitly selected.")
        ],
        "crafts": [
            ("HOOK / CRAFT ITEM REVEAL", "Open on the complete craft product or kit so the actual included contents are clear."),
            ("FULL KIT VIEW", "Show only the pieces visible or explicitly confirmed as included."),
            ("TEXTURE / TOOL DETAIL", "Highlight a visible texture, edge or tool part without inventing material properties."),
            ("SIMPLE MAKING ACTION", "Show one safe, plausible craft action only if supported by the kit; do not add extra tools or finished results."),
            ("CTA / CRAFT HERO", "Finish with the original product or kit neatly visible; no on-screen text unless explicitly selected.")
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
        # A user's explicit subcategory outranks ambiguous words in a product name.
        if subtype in {"bag_wallet", "wallet", "card_holder"}:
            category = "wallet"
        elif subtype in {"bag_backpack", "backpack", "bag_laptop"}:
            candidates = ["backpack_demo", "bag_daily_carry", "bag_tabletop_reveal", "lifestyle", "cinematic"]
        elif subtype in {"bag_sling", "sling_bag", "bag_handbag", "handbag", "bag_tote"}:
            candidates = ["sling_bag_lifestyle", "handbag_showcase", "bag_daily_carry", "bag_tabletop_reveal", "bag_flatlay"]
        elif any(term in product_words for term in ("wallet", "dompet", "card holder", "cardholder", "coin purse")):
            category = "wallet"
        elif any(term in product_words for term in ("backpack", "rucksack", "beg galas", "beg sekolah", "beg laptop")):
            candidates = ["backpack_demo", "bag_daily_carry", "bag_tabletop_reveal", "lifestyle", "cinematic"]
        elif any(term in product_words for term in ("sling", "crossbody", "beg silang", "tote bag", "handbag", "beg tangan")):
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


_RECENT_PRESENTATION_CHOICES = {}
_PRESENTATION_PROFILES = (
    "centered hero composition, soft side lighting, detail-first reveal followed by a full-product hero, and a calm gradual pace",
    "off-centre composition with clean negative space, diffused high-key lighting, full-product view before one detail close-up, and two clean match cuts",
    "three-quarter product composition, restrained rim lighting where compatible with the style, visible-edge detail followed by a stable hero, and measured cinematic pacing",
    "contextual wide view followed by a product-focused close-up, natural-looking light, one clean reframe, and relaxed lifestyle pacing",
    "macro or close detail first only when useful for the product, controlled highlights, then ease back to the complete product with a deliberate pace",
    "overhead or slightly angled composition only when suitable, even soft lighting, detail-to-hero sequence, and a clean editorial rhythm",
    "lower three-quarter framing only when it suits the product, broad diffused lighting, silhouette before detail, and confident but controlled pacing",
    "front-facing hero with soft backlight, one visible-detail reveal, then a stable closing hero with gentle pacing",
    "asymmetrical composition, neutral balanced lighting, side-detail view followed by the complete product, and a minimal edit rhythm",
    "close-to-medium shot sequence, warm light only when it suits the selected style and product, one motivated match cut, and brisk but clean pacing",
    "clear full-product view first, subtle reflected highlights, one detail shot, then a steady final hold",
    "contextual composition with a softly separated background, natural-looking light, wide-to-close progression, and restrained pacing",
)


def _presentation_variation(style_key, product_type, product_subtype=""):
    """Choose a fresh composition/light/edit profile while preserving the selected style."""
    key = (str(style_key or "auto"), str(product_type or "other"), str(product_subtype or ""))
    recent = _RECENT_PRESENTATION_CHOICES.setdefault(key, deque(maxlen=3))
    available = [index for index in range(len(_PRESENTATION_PROFILES)) if index not in recent]
    index = random.SystemRandom().choice(available or list(range(len(_PRESENTATION_PROFILES))))
    recent.append(index)
    return (
        "PRESENTATION VARIATION: Keep the selected visual style recognizably consistent, but for this generation use "
        + _PRESENTATION_PROFILES[index] + ". This profile varies composition, lighting, shot order and pacing; "
        "do not change product identity, invent features or accessories, replace a user-selected location, "
        "or override the selected camera movement, music, voice, model or category-specific realism rules. For connected clips, preserve the same setting, "
        "lighting direction, product orientation and final-frame handoff."
    )



def _compact_storyboard(product, scene, motion, style, product_type, subtype):
    _, style_name, _ = resolve(style)
    scenes = _category_specific_scenes(product_type, product, subtype)
    times = ('0–2s', '2–4s', '4–6s', '6–8s', '8–10s')
    lines = ['VIDEO PROMPT — 10 SECONDS', 'Vertical 9:16. Style: ' + style_name,
             'PRODUCT: ' + str(product).strip(), 'SETTING: ' + str(scene).strip(),
             'CAMERA: ' + str(motion).strip()]
    lines.extend(t + ': ' + direction for t, (_, direction) in zip(times, scenes))
    return '\n'.join(lines)


def _concise_video_prompt(product, scene, motion, style, product_type, subtype, part=0):
    """One clear visual brief; selected audio and text are appended by the bot."""
    _, style_name, _ = resolve(style)
    scenes = _category_specific_scenes(product_type, product, subtype)
    actions = [str(item[1]).strip() for item in scenes[:3]]
    while len(actions) < 3:
        actions.append("Keep the product naturally visible.")
    label = "VIDEO PROMPT — 10 SECONDS" if not part else "VIDEO PROMPT — PART " + str(part) + " (10 SECONDS)"
    continuity = (" Continue directly from Part 1's final frame, with the same product, setting and camera position; finish with a natural closing view." if part > 1 else
                  " End on a steady product view ready for Part 2 to continue." if part == 1 else "")
    return "\n\n".join((
        label + "\nVertical 9:16, realistic footage. " + str(style_name) + "." + continuity,
        "Use the uploaded product image as the master reference. " + str(product).strip(),
        "SETTING: " + str(scene or "A natural setting suited to the product").strip() + ".",
        "ACTION: 0–3s: " + actions[0] + " 3–7s: " + actions[1] + " 7–10s: " + actions[2],
        "CAMERA: " + str(motion).strip(),
        "Keep the product's visible design, colour, details and proportions identical to the reference."
    ))


def build_prompt(mode, product, scene, motion, style='auto', duration=10, concept='', product_type='other', storyboard_override=None, split=None, universal_custom=False, product_subtype='', prompt_language='Malay', concise=False):
    # Preserve the historical API behavior: a 20-second call without an explicit
    # split choice still returns two connected 10-second prompts.
    if split is None:
        split = duration in (20, 30)
    style = _resolve_auto_style(style, product_type, product, product_subtype) if mode == 'storyboard' else style
    if concise and mode == 'storyboard':
        if split and duration > 10:
            return "\n\n".join(
                _concise_video_prompt(product, scene, motion, style, product_type, product_subtype, part=index)
                for index in range(1, duration // 10 + 1)
            )
        if duration == 10:
            return _concise_video_prompt(product, scene, motion, style, product_type, product_subtype)
    if split and duration > 10:
        # Generate connected 10-second prompts while retaining the same style and product context.
        presentation_variation = _presentation_variation(style, product_type, product_subtype)
        parts = [
            _build_single_prompt(mode, product, scene, motion, style, part=index, duration=10,
                                 concept=concept, product_type=product_type, storyboard_override=storyboard_override, universal_custom=universal_custom, product_subtype=product_subtype, prompt_language=prompt_language)
            + "\n\n" + presentation_variation
            + "\n\n" + _creative_variation(product_type, product, index, product_subtype)
            for index in range(1, duration // 10 + 1)
        ]
        return "\n\n".join(
            ("=== KLIPPO PART " + str(index + 1) + " ===\n\n" + part) if index else part
            for index, part in enumerate(parts)
        )
    presentation_variation = _presentation_variation(style, product_type, product_subtype)
    return (_build_single_prompt(mode, product, scene, motion, style, part=0, duration=duration,
                                concept=concept, product_type=product_type, storyboard_override=storyboard_override, universal_custom=universal_custom, product_subtype=product_subtype, prompt_language=prompt_language)
            + "\n\n" + presentation_variation
            + "\n\n" + _creative_variation(product_type, product, 0, product_subtype))


def _build_single_prompt(mode, product, scene, motion, style='auto', part=0, duration=10, concept='', product_type='other', storyboard_override=None, universal_custom=False, product_subtype='', prompt_language='Malay'):
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
        'bag': "PRODUCT CATEGORY DIRECTION: Treat this as the explicitly selected bag subtype, when supplied. Do not reinterpret a handbag as a wallet, backpack, tote or sling from brand or name keywords. Choose only the matching presentation. Do not assume exact materials, compartments, hardware or accessories unless stated in the name.",
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
        category_direction += " " + opening_direction(product_type, prompt_language)
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
    category_direction += (
        " MODEL–PRODUCT USE PRIORITY: If the user selected a human model, that model MUST visibly use, wear, operate, carry, serve or otherwise demonstrate the named product's actual intended purpose, as appropriate to the product category. "
        "The model must not merely stand beside it, point at it, hold it motionless, pose, or rotate it for the camera. Show believable hand/body contact and the product remaining identifiable during the action. "
        "Do not add a model when the user selected product-only/no model; use reference-safe product-focused presentation instead. "
        "Never invent unseen functions, included accessories, performance results or unsafe actions. "
    )
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
        hook = product_hook(product, prompt_language)
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
                scenes = _category_specific_scenes(product_type, product, product_subtype)
                clip_label = "SECOND CLIP 10s" if part == 2 else "THIRD CLIP 10s" if part == 3 else "CONTINUATION CLIP 10s"
                beat_plan = (
                    clip_label + ": 0–2s CONTINUITY BRIDGE — resume from the exact full-product frame held at the end of the previous clip and do not repeat the hook; "
                    + "2–4s CATEGORY ACTION — " + scenes[3][1] + " "
                    + "4–6s VISIBLE DETAIL — " + scenes[2][1] + " "
                    + "6–8s NATURAL FOLLOW-THROUGH — continue the same setting and product orientation; "
                    + "8–10s HERO HOLD — finish with the complete unchanged product clearly visible. "
                    + "Do NOT repeat the opening hook or restart the reveal. "
                )
            elif not (storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4):
                scenes = _category_specific_scenes(product_type, product, product_subtype)
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
                + ("If voice or on-screen text is selected, use varied, natural product-specific wording and one concise CTA that match the selected options; avoid stock openings such as “Kenali produk ini” and never invent claims, discounts, prices, urgency or availability. "
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
            concept_rule = ("CREATIVE IDEA: " + _prompt_text(concept, "") + " " if concept and concept.strip() else "")
            return (
                "VIDEO PROMPT — " + str(duration) + " SECONDS" + (" | PART " + str(part) if part else "") + "\n"
                "Vertical 9:16, realistic product video, exactly " + str(duration) + " seconds.\n"
                + "STYLE: " + style_name + " — " + _prompt_text(style_template, "Use a realistic product-focused presentation.") + "\n"
                + "PRODUCT: " + product + "\n" + concise_category_direction + concise_framework
                + (" UNIVERSAL SAFETY RULES: Preserve visible product details; invent no features or claims."
                   if product_type == "other" or universal_custom else "") + "\n"
                + "SETTING: " + _prompt_text(scene, "A realistic setting suited to the product.") + " CAMERA: " + _prompt_text(camera, "Use one restrained camera move and keep the product stable.") + "\nCAMERA PRIORITY: Follow the selected CAMERA instruction if STYLE suggests a conflicting move; use only one camera movement.\n"
                + "PRODUCT LOCK: Preserve the reference product's visible design, colour, pattern, branding and proportions. Do not invent features or accessories.\n"
                + hook_rule + beat_plan + " " + concept_rule + " " + doodle_rule + " "
                + "Keep actions natural and the product consistent. Follow the selected text, audio and visual options. For AI-generated voice, use varied, natural product-specific wording and one concise CTA in " + ("English" if str(prompt_language or "Malay").casefold() == "english" else "Bahasa Melayu Malaysia") + "; avoid stock openings such as “Kenali produk ini” and never invent claims, discounts, prices, urgency or availability. If a user-supplied script is selected, use it exactly and add no dialogue."
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
            generic_scenes = _category_specific_scenes(product_type, product, product_subtype)
            if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
                curated_items = list(storyboard_override)
                generic_scenes = [
                    ("OPENING / PRODUCT REVEAL", "Establish the exact product clearly in a coherent setting; no on-screen text."),
                    (str(curated_items[0].get("shot", "CREATIVE BEAT 1")), str(curated_items[0].get("direction", ""))),
                    (str(curated_items[1].get("shot", "CREATIVE BEAT 2")), str(curated_items[1].get("direction", ""))),
                    (str(curated_items[2].get("shot", "CREATIVE BEAT 3")), str(curated_items[2].get("direction", ""))),
                    ("CREATIVE FINISH / HERO HOLD", str(curated_items[3].get("direction", "")) + " Finish on a stable, full-product hero frame."),
                ]
            # Enforce this after curated storyboard selection too, so style libraries cannot suppress real product use.
            usage_scene = _PRODUCT_USAGE_SCENES.get(str(product_type or "").casefold())
            if usage_scene and len(generic_scenes) >= 4:
                generic_scenes[3] = usage_scene
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
                + "\n\nKeep transitions natural, camera movement restrained and product geometry stable throughout. For functional products, visibly demonstrate one genuine, category-appropriate use action; camera movement or a static hero shot alone does not count. If the function is unclear, show safe handling or placement without inventing a use."
            )
            if storyboard_override and isinstance(storyboard_override, (list, tuple)) and len(storyboard_override) == 4:
                curated_direction = storyboard_text
            else:
                rules = storyboard_text
        return (
            "VIDEO PROMPT — " + str(duration) + " SECONDS" + (" | PART " + str(part) if part else "") + "\n"
            "Realistic vertical 9:16 product ad, exactly " + str(duration) + " seconds.\n"
            "PRODUCT: " + product + "\n" + category_direction + "\n"
            + "STYLE: " + style_name + " — " + _prompt_text(style_template, "Use a realistic product-focused presentation.") + "\n"
            + "SETTING: " + _prompt_text(scene, "A realistic setting suited to the product.") + "\nCAMERA: " + _prompt_text(camera, "Use one restrained camera move and keep the product stable.") + "\nCAMERA PRIORITY: Follow the selected CAMERA instruction if STYLE suggests a conflicting move; use only one camera movement.\n"
            + (curated_direction if curated_direction else
               ((hook_direction if part != 2 else "Continue seamlessly from Part 1; do not repeat the hook.") + "\n" + rules))
            + (("\nCREATIVE IDEA: " + _prompt_text(concept, "")) if concept else "")
            + "\nNatural movement. For AI-generated voice, use varied, natural product-specific wording and one concise CTA in " + ("English" if str(prompt_language or "Malay").casefold() == "english" else "Bahasa Melayu Malaysia") + "; avoid stock openings such as “Kenali produk ini” and never invent claims, discounts, prices, urgency or availability. Preserve any user-supplied script exactly and add no dialogue. No added on-screen text or watermark."
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
        "STYLE: " + _prompt_text(art, "Use a realistic product-focused presentation.") + "\n"
        "SETTING: " + _prompt_text(scene, "A realistic setting suited to the product.") + "\n"
        + direction + "\n"
        + "Preserve the product's visible design and packaging; invent no features. "
        "Natural movement, clean transitions, no added on-screen text or watermark. "
        "For AI-generated voice, use varied, natural product-specific wording and one concise CTA in " + spoken_language + "; avoid stock openings such as “Kenali produk ini” and never invent claims, discounts, prices, urgency or availability. Preserve any user-supplied script exactly and add no dialogue."
    )