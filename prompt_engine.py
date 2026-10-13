"""Detailed, reference-safe AI video prompt templates for KLIPPO."""

CAMERAS = {
    "orbit": "A restrained camera arc of at most 30 degrees with subtle parallax. Never reveal or fabricate an unseen side.",
    "push": "A smooth slow dolly-in from a balanced medium product shot to a crisp detail, with no digital warping.",
    "side": "A measured left-to-right lateral camera slide with gentle depth separation and stable product proportions.",
    "static": "A locked premium studio composition with delicate lighting movement and a subtle focus transition.",
}

def build_prompt(mode, product, scene, motion):
    camera = CAMERAS.get(motion, CAMERAS["push"])
    identity = (
        "REFERENCE LOCK: Treat the uploaded photograph as the sole visual source of truth. "
        "Preserve the exact product silhouette, proportions, material appearance, visible colors, "
        "packaging, labels, branding, count and orientation. Use the user's optional details only "
        "when consistent with what is visible. Never infer unseen surfaces or specifications."
    )
    art = (
        f"ART DIRECTION: Premium commercial product cinematography. Environment: {scene}. "
        "Clean, intentional negative space; product is the unmistakable hero. Soft large-key illumination, "
        "controlled fill, realistic contact shadow and restrained edge highlights. Preserve true-to-reference "
        "surface texture and legibility; avoid excessive bloom or artificial plastic shine. "
        "Use elegant pacing, physically plausible movement and stable framing."
    )
    negative = (
        "STRICT EXCLUSIONS: No invented features, extra accessories, duplicated or morphing products, "
        "changing logos or typography, people or hands, random props, floating geometry, distorted edges, "
        "flicker, jitter, abrupt exposure shifts, captions, subtitles, UI or watermarks. "
        "Do not attempt a full 360-degree rotation from one reference image."
    )
    if mode == "storyboard":
        direction = (
            "STORYBOARD: Produce ONE continuous 10-second 9:16 video with six clearly motivated shots, "
            "not six disconnected clips. Maintain the same product and set throughout.\n"
            "SHOT 1 | 0.0-1.5s | HOOK: A striking but faithful tight crop on a visible defining detail; "
            "controlled punch-in and a refined light sweep.\n"
            "SHOT 2 | 1.5-3.0s | REVEAL: Transition into a full-product hero composition; "
            "slow lateral reveal, preserve all reference proportions.\n"
            "SHOT 3 | 3.0-5.0s | CONTEXT: Show the product in the selected environment with a grounded "
            "contact shadow and gentle parallax, without adding unsupported usage claims or props.\n"
            "SHOT 4 | 5.0-7.0s | DETAIL: Highlight only a texture, finish, component or label actually "
            "visible in the source image. Slow macro-style push; keep details accurate.\n"
            "SHOT 5 | 7.0-8.5s | HERO: Premium centered three-quarter-feel composition using only "
            "supported visible geometry. Camera direction: " + camera + "\n"
            "SHOT 6 | 8.5-10.0s | CLOSING: Settle on a clean full-product packshot, gentle pull-back "
            "and graceful fade, leaving uncluttered space without generating any text.\n"
            "TRANSITIONS: Motivated match cuts, soft dissolves or subtle movement continuity; "
            "no distracting spins or excessive effects. Each shot must flow naturally into the next."
        )
    else:
        direction = (
            "SINGLE-SCENE CREATIVE DIRECTION: One continuous 10-second cinematic product shot with "
            "a clear beginning, development and closing, not a slideshow. Start with a balanced "
            "medium-wide composition and a moment of visual anticipation (0-2s); develop with "
            "this camera movement (2-7s): " + camera + " End on a clean, steady hero packshot "
            "(7-10s) with refined easing and a subtle light accent. Keep the product sharp and "
            "recognizable, with believable depth, natural reflections and deliberate composition. "
            "No cuts or invented viewpoints."
        )
    return (
        "KLIPPO | PROFESSIONAL IMAGE-TO-VIDEO PRODUCTION PROMPT\n"
        "OUTPUT: 10 seconds; portrait 9:16; high-quality realistic product commercial; "
        "one coherent deliverable; no on-screen text.\n\n"
        "PRODUCT: " + product + "\n\n" + identity + "\n\n" + art + "\n\n"
        + direction + "\n\n" + negative + "\n\n"
        "FINAL QUALITY CHECK: Consistent identity in every frame, natural physics, clean edges, "
        "stable illumination, smooth temporal coherence and polished affiliate-ad aesthetics. "
        "If the reference does not support a requested viewpoint, use a safe crop or modest "
        "2D camera movement instead of hallucinating the product."
    )
