"""Curated, fixed KLIPPO storyboard prompt templates.

The creative wording in this module is intentionally static. Only verified product
reference text, selected camera movement, and confirmed optional details are inserted.
No generative variation engine rewrites these templates.
"""
import random
from prompt_catalog import product_hook, resolve

CAMERA = {
    "orbit": "A restrained camera arc of at most 15 degrees, staying reference-facing; never reveal unseen sides.",
    "push": "A smooth slow dolly-in from a balanced medium product shot to a crisp visible detail, with no digital warping.",
    "side": "A measured short lateral camera slide with stable proportions and no newly revealed unseen surfaces.",
    "static": "A locked reference-facing camera with only a subtle focus transition and gentle lighting movement.",
    "auto": "A smooth slow dolly-in from a balanced medium product shot to a crisp visible detail, with no digital warping.",
}

TEMPLATES = {
    "luxury": {
        "name": "💎 Luxury Product",
        "setting": "a clean premium dark or neutral studio, chosen to complement the uploaded product without distracting props",
        "look": "Refined luxury product cinematography, soft rim highlights, rich but accurate material texture, controlled reflections, natural contact shadows and sophisticated slow movement.",
        "graphics": "No on-screen text, captions, icons or decorative graphics unless explicitly requested by the user.",
    },
    "cinematic": {
        "name": "🎬 Cinematic Premium",
        "setting": "a clean cinematic studio background that complements the exact product reference",
        "look": "Premium realistic commercial lighting, soft key light, restrained highlights, natural shadows, tactile material detail and a calm cinematic pace.",
        "graphics": "No on-screen text, captions, icons or decorative graphics unless explicitly requested by the user.",
    },
    "minimal": {
        "name": "✨ Minimal & Clean",
        "setting": "a bright, uncluttered neutral studio with generous negative space",
        "look": "Minimal editorial product photography, even soft daylight, clean composition, subtle depth and gentle movement without distracting effects.",
        "graphics": "No on-screen text, captions, icons or decorative graphics unless explicitly requested by the user.",
    },
    "dynamic": {
        "name": "⚡ Dynamic Product",
        "setting": "a polished modern product studio with a restrained complementary background",
        "look": "Engaging but controlled product-ad pacing, precise reframing, crisp product detail and smooth match-like transitions while preserving realistic geometry.",
        "graphics": "No on-screen text, captions, icons or decorative graphics unless explicitly requested by the user.",
    },
    "white_doodle": {
        "name": "✏️ White Doodle",
        "setting": "a clean product-ad setting with enough uncluttered space around the product for white graphic overlays",
        "look": "Realistic product footage with restrained camera movement and consistent light. Add only thin white 2D doodle overlays outside the product silhouette: a few tiny sparkles and one clean curved arrow. Never let graphics cover the logo, label or important product details.",
        "graphics": "White doodle graphics are explicitly requested by this preset. Do not invent words, claims, prices or captions. If accurate overlay rendering is unreliable, leave clean footage for post-production overlays.",
    },
    "fashion": {
        "name": "👗 Fashion Reference Lock",
        "setting": "the same environment and viewpoint shown in the uploaded reference image",
        "look": "Natural realistic fashion footage, soft believable light, authentic fabric texture and subtle human movement. Preserve the same visible person, face, hijab, outfit, garment pattern, accessories and proportions exactly as shown. Do not invent a person if none is visible.",
        "graphics": "No on-screen text, captions or decorative graphics unless explicitly requested by the user.",
    },
}

def _clean_reference(product):
    value = (product or "").strip()
    # The bot's vision-analysis output is internal metadata, not prompt copy.
    lines = []
    for line in value.splitlines():
        key, sep, val = line.partition(":")
        if sep and key.strip().upper() in {
            "NAMA_PRODUK", "KATEGORI", "TEKS_DISAHKAN", "CIRI_BERTULIS",
            "CIRI_VISUAL", "VISIBLE OBSERVATIONS", "OPTIONAL USER DETAILS",
            "VERIFIED IMAGE OBSERVATIONS", "USER-PROVIDED PRODUCT DETAILS",
        }:
            val = val.strip()
            if val and val.upper() not in {
                "TIADA", "TIDAK PASTI", "UNKNOWN", "NONE", "N/A", "UNAVAILABLE",
            }:
                lines.append(f"{key.strip()}: {val}")
            continue
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines) or "the product shown in the uploaded reference image"

def _select_style(style):
    if style == "auto":
        return random.choice(["luxury", "cinematic", "minimal", "dynamic", "white_doodle"])
    if style in TEMPLATES:
        return style
    try:
        key = resolve(style)[0]
        return key if key in TEMPLATES else "cinematic"
    except Exception:
        return "cinematic"

def build_curated_storyboard(product, motion="push", style="luxury", duration=10, user_details="", scene=""):
    """Build from a saved template. This deliberately does not call the variation engine."""
    key = _select_style(style)
    template = TEMPLATES[key]
    reference = _clean_reference(product)
    camera = CAMERA.get(motion, CAMERA["auto"])
    selected_scene = (scene or "").strip()
    if selected_scene and "selected to complement the exact product reference" not in selected_scene.lower():
        template = dict(template)
        template["setting"] = selected_scene
    details = (user_details or "").strip()
    if details:
        reference += "\nUSER-PROVIDED DETAILS (use only if consistent with the image): " + details
    hook = product_hook(reference) if key in ("white_doodle", "dynamic") else None
    hook_line = (
        "OPENING HOOK: Use exactly this verified product-identification wording: '" + hook +
        "'. Do not add any other text or unsupported claims."
        if hook else "NO ON-SCREEN HOOK TEXT: Start with the product image. Do not guess its name, category, benefits or popularity."
    )
    if key == "white_doodle":
        hook_line += " White doodle accents are allowed as non-text graphics, but do not let them cover the product."
    part1 = (
        f"KLIPPO | STORYBOARD | {template['name']}\n"
        f"OUTPUT: One cohesive vertical 9:16 product advertisement, EXACT DURATION: 10 seconds.\n\n"
        f"PRODUCT REFERENCE: {reference}\n\n"
        "REFERENCE LOCK: Treat the uploaded photograph as the sole visual source of truth. Preserve the exact visible product silhouette, proportions, material appearance, colors, packaging, labels, branding, count and orientation. Never invent unseen surfaces, specifications, accessories or product features.\n\n"
        f"STYLE: {template['look']}\n"
        f"SETTING: {template['setting']}\n"
        f"CAMERA: {camera} Stay reference-facing; never invent unseen sides.\n\n"
        "PRODUCT EVIDENCE: Use only details clearly visible in the image or explicitly supplied by the user and consistent with it. Preserve legible printed wording exactly. Packaging claims are label text, not independently verified benefits. Omit uncertain details. Never print internal field names, empty fields or placeholders.\n\n"
        f"{hook_line}\n\n"
        "TIMING: 0-2s establish the product with the verified hook only if one is available; 2-5s reveal the complete product; 5-8s emphasize one genuinely visible detail; 8-10s return to a stable full-product hero frame and HOLD for a seamless Part 2 handoff. No closing fade in Part 1.\n\n"
        f"GRAPHICS: {template['graphics']}\n\n"
        "CONTINUITY: Keep product shape, color, visible logo, count, orientation, setting and lighting consistent throughout. No morphing, duplicated objects, fake rotations, invented props, flicker, jitter or digital warping. Keep all visible branding unobstructed."
    )
    if duration != 20:
        return part1
    part2 = (
        f"KLIPPO | STORYBOARD | {template['name']} | PART 2\n"
        "OUTPUT: One cohesive vertical 9:16 product advertisement, EXACT DURATION: 10 seconds.\n\n"
        f"PRODUCT REFERENCE: {reference}\n\n"
        "REFERENCE LOCK: Use the same uploaded photograph as the sole source of truth. Preserve the exact product identity, silhouette, visible colors, label, logo, count and orientation. Do not invent unseen sides or details.\n\n"
        f"STYLE: {template['look']}\nSETTING: {template['setting']}\nCAMERA: {camera}\n\n"
        "CONTINUITY HANDOFF: Begin from the exact final held frame of Part 1, matching crop, product position, orientation, background, light direction and color. Do not restart with a new angle or scene.\n\n"
        "TIMING: 0-2s continue the held frame with subtle motion; 2-6s show one other genuinely visible detail without revealing unseen surfaces; 6-8s ease back to the full product; 8-10s finish with an elegant stable hero frame and a gentle fade. Do not repeat the opening hook.\n\n"
        f"GRAPHICS: {template['graphics']}\n\n"
        "STRICT EXCLUSIONS: No product morphing, changed labels, invented accessories, unsupported claims, extra objects, flicker, jitter, digital warping or unrequested text. Keep visible branding unobstructed."
    )
    return part1 + "\n\n=== KLIPPO PART 2 ===\n\n" + part2
