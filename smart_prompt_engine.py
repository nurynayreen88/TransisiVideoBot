"""Additive creative-variation engine for KLIPPO prompt generation.

Uses the existing visual-analysis text and user-selected scene/camera controls.
No external API calls, no database writes, and no changes to rendering workflows.
"""
from __future__ import annotations

import random
import re

SCENE_VARIANTS = {
    "auto": [
        "a bright lived-in modern home corner with soft window light and realistic surfaces",
        "a tasteful boutique display area with uncluttered shelves and warm practical lighting",
        "a calm café or lifestyle corner with natural daylight and softly blurred background details",
        "a premium neutral studio with a subtle textured backdrop and grounded contact shadows",
        "an airy outdoor terrace in soft morning light, with the product protected from visual clutter",
        "a refined evening interior with warm lamps and gentle background bokeh",
        "a clean dressing area with a full-length mirror and believable everyday details",
        "a minimalist sunlit corner with pale stone, linen or wood textures",
    ],
    "studio": [
        "a premium warm-beige studio with soft directional key light and realistic floor contact",
        "a bright editorial studio with ivory backdrop and gentle natural shadows",
        "a muted sage or sand-toned studio backdrop chosen to complement the reference colours",
        "a softly graduated neutral studio with subtle edge light and generous negative space",
    ],
    "dark": [
        "a dark charcoal luxury set with restrained warm rim lighting and a realistic grounded surface",
        "a deep espresso studio with soft amber highlights and no distracting props",
        "a refined midnight-toned set with controlled reflections and natural material response",
    ],
    "home": [
        "a bright bedroom dressing corner with soft morning window light and realistic furnishings",
        "a welcoming living-room corner with linen, wood and gentle daylight",
        "a neat entryway or dressing area that feels naturally used, not like a staged showroom",
        "a cozy home corner in late-afternoon light with believable background depth",
    ],
    "nature": [
        "a shaded garden walkway with soft daylight and calm green background blur",
        "an airy balcony with plants and gentle morning light, keeping the product clearly separated",
        "a quiet outdoor terrace with warm late-afternoon light and restrained natural textures",
    ],
    "minimal": [
        "a sunlit minimalist interior with pale stone, clean lines and subtle natural shadows",
        "a bright neutral corner with soft ivory and beige surfaces and plenty of negative space",
        "a modern uncluttered setting with light wood, linen and diffused daylight",
    ],
}

CAMERA_VARIANTS = [
    "begin in a balanced medium shot, then make a gentle push-in toward one visible detail before easing back",
    "use a smooth lateral slide of only a small distance, keeping product proportions and framing stable",
    "start with a close detail that is genuinely visible, then gently widen to reveal the complete product",
    "hold a calm reference-facing composition while focus and light subtly shift across the real surface",
    "use a modest over-the-shoulder or mirror-facing framing only when supported by the reference photograph",
    "make a slow diagonal camera drift with physically plausible parallax; never orbit into unseen sides",
    "alternate a steady full-product view with one controlled detail crop, connected by a soft match cut",
]

LIGHTING_VARIANTS = [
    "soft morning window light with natural shadow falloff",
    "warm late-afternoon light with realistic highlights and no orange colour cast",
    "large diffused studio key light with gentle fill and a subtle edge highlight",
    "soft overcast daylight with accurate colours and low-contrast shadows",
    "warm practical interior lighting balanced with neutral fill so product colours remain true",
    "subtle premium rim light that reveals texture without plastic shine",
]

MOOD_VARIANTS = [
    "authentic casual creator footage, relaxed and believable",
    "polished premium commercial, restrained and elegant",
    "warm lifestyle storytelling, natural rather than theatrical",
    "bright, friendly and contemporary, with confident but unhurried pacing",
    "editorial product film with clean composition and tactile detail",
    "playful, spontaneous energy without exaggerated acting or unsafe actions",
]

FASHION_ACTIONS = [
    "the person makes one small natural adjustment, then shows the outfit from the same reference-facing view",
    "the person takes one relaxed step and returns to a comfortable pose, preserving the exact outfit and accessories",
    "the person gently smooths a visible sleeve or fabric edge, then holds still so the real texture can be seen",
    "the person makes a subtle side turn only within the visible reference-safe range, then returns to the original pose",
    "the person lifts or adjusts a visible handbag naturally, without hiding or changing the garment",
    "the person takes a casual mirror-selfie pause, slightly reframes the phone, and settles into a natural pose",
]
PRODUCT_ACTIONS = [
    "keep the product grounded while the camera reveals one genuinely visible material or design detail",
    "use a gentle light reveal across the existing surface, then settle on a clear full-product hero view",
    "move from a clean full-product composition to a close detail crop and back, without changing product geometry",
    "use a restrained foreground-to-background focus shift while the product remains stationary and recognizable",
    "let the camera reveal the packaging and visible components in a deliberate order without adding props",
    "finish with a steady hero composition that makes the product silhouette, colour and visible branding easy to inspect",
]
HOME_ACTIONS = [
    "show the item in a believable everyday context, then return to a clear unobstructed product view",
    "use one small practical interaction only if it is supported by the visible product and user details",
    "keep the product stable while the camera gently reveals its visible finish, shape and scale",
]

def _category(product: str) -> str:
    text = (product or "").lower()
    if any(w in text for w in ("baju", "kurung", "tudung", "hijab", "dress", "fashion", "clothing", "outfit", "garment", "kebaya", "jubah", "abaya", "blouse", "skirt", "pants")):
        return "fashion"
    if any(w in text for w in ("sofa", "kerusi", "chair", "meja", "table", "katil", "bed", "lampu", "lamp", "rak", "shelf", "home")):
        return "home"
    return "product"

def _scene_bucket(scene: str) -> str:
    value = (scene or "").lower()
    if any(w in value for w in ("selected to complement", "auto", "automatik")):
        return "auto"
    if any(w in value for w in ("dark", "gelap", "luxury", "mewah")):
        return "dark"
    if any(w in value for w in ("home", "rumah", "bedroom", "living")):
        return "home"
    if any(w in value for w in ("nature", "natural setting", "alam", "garden", "outdoor")):
        return "nature"
    if any(w in value for w in ("minimal", "cerah", "bright minimalist")):
        return "minimal"
    return "studio"

def choose_variation(product: str, scene: str, motion: str = "push",
                     style: str = "auto", mode: str = "normal",
                     part: int = 0, user_concept: str | None = None,
                     seed: int | None = None) -> dict[str, str]:
    """Choose one coherent variation pack; pass the same pack to connected clips."""
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    category = _category(product)
    bucket = _scene_bucket(scene)
    setting = rng.choice(SCENE_VARIANTS[bucket])
    camera = rng.choice(CAMERA_VARIANTS)
    lighting = rng.choice(LIGHTING_VARIANTS)
    mood = rng.choice(MOOD_VARIANTS)
    if category == "fashion":
        action = rng.choice(FASHION_ACTIONS)
    elif category == "home":
        action = rng.choice(HOME_ACTIONS)
    else:
        action = rng.choice(PRODUCT_ACTIONS)
    concept = (user_concept or "").strip()
    if concept:
        # Keep the user's chosen concept as the creative lead; don't replace it.
        mood = concept
    # Camera choice remains subordinate to the explicit user-selected motion control.
    motion_text = (motion or "push").lower()
    if "static" in motion_text or "locked" in motion_text:
        camera = "use a locked reference-facing frame; vary only focus and soft lighting, with no camera travel"
    elif "side" in motion_text or "lateral" in motion_text:
        camera = "use a controlled left-to-right lateral slide, maintaining stable proportions and reference-facing geometry"
    elif "orbit" in motion_text or "arc" in motion_text:
        camera = "use only a restrained camera arc of at most 20 degrees; never reveal unseen surfaces"
    elif "push" in motion_text or "dolly" in motion_text or "zoom" in motion_text:
        camera = "use a smooth, restrained push-in and ease back, avoiding digital warping or aggressive zoom"
    if part == 2:
        action = "resume from the exact final frame of Part 1, then reveal a different genuinely visible detail before returning to the full-product hero view"
    return {
        "category": category,
        "setting": setting,
        "camera": camera,
        "lighting": lighting,
        "mood": mood,
        "action": action,
        "concept": concept,
    }

def format_variation(variation: dict[str, str]) -> str:
    """Render the variation pack as explicit instructions for a video model."""
    return (
        "SMART CREATIVE VARIATION (selected for this generation):\n"
        f"Concept/mood: {variation['mood']}.\n"
        f"Environment variation: {variation['setting']}.\n"
        f"Action: {variation['action']}.\n"
        f"Camera direction: {variation['camera']}.\n"
        f"Lighting: {variation['lighting']}.\n"
        "Keep one coherent scene within this clip. Variation must never alter the product's real design, "
        "visible colour, pattern, packaging, branding, count or proportions. Do not invent unseen sides, "
        "features, props or unsupported claims. No on-screen text unless the user explicitly supplied exact wording."
    )
