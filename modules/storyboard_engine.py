"""Free, offline prompt builder for a four-panel product storyboard.

This module makes no network/API calls and does not generate images or video.
It creates a copy-ready text prompt that users can run in an image/video tool
they already have access to.
"""


STYLE_LABELS = {
    "product_only": "Product-only campaign: do not include a model, hands, or unrelated products.",
    "model_holding": "A suitable adult model naturally holding or wearing the exact product.",
    "model_lifestyle": "A suitable adult model featuring the exact product in a believable lifestyle scene.",
}
ENVIRONMENT_LABELS = {
    "studio": "premium minimalist studio, soft controlled light, elegant neutral background",
    "home": "tasteful modern home, warm natural daylight, realistic lived-in details",
    "cafe": "modern stylish cafe, warm ambient light, softly blurred background",
}
GOAL_LABELS = {
    "shopee": "Shopee Affiliate: clear, credible product presentation that helps shoppers inspect the real product.",
    "tiktok": "TikTok Viral: a strong visual hook and dynamic framing while keeping the product clear and believable.",
}


def build_storyboard_prompt(goal, style, environment, attributes=None):
    """Return a complete, copy-ready four-panel storyboard prompt without API calls."""
    goal_text = GOAL_LABELS.get(goal, GOAL_LABELS["shopee"])
    style_text = STYLE_LABELS.get(style, STYLE_LABELS["product_only"])
    environment_text = ENVIRONMENT_LABELS.get(environment, ENVIRONMENT_LABELS["studio"])
    attrs = attributes if isinstance(attributes, dict) else {}
    observed = []
    for key, label in (
        ("product_type", "Product type"),
        ("colors", "Visible colours"),
        ("shape", "Shape"),
        ("material", "Material"),
        ("visible_details", "Visible details"),
    ):
        value = attrs.get(key)
        if isinstance(value, str) and value.strip():
            observed.append(f"{label}: {value.strip()}.")
    observations = " ".join(observed) or (
        "Inspect the uploaded product reference directly. Use it as the sole source of truth "
        "for product-specific appearance; do not invent unseen details or specifications."
    )

    return f"""KLIPPO — FOUR-PANEL PRODUCT STORYBOARD PROMPT

Create ONE cohesive, professional 9:16 vertical storyboard sheet containing EXACTLY FOUR clearly separated panels arranged vertically from top to bottom (Panel 1, Panel 2, Panel 3, Panel 4). This is a storyboard layout, not a finished video. Keep the same product identity, model (if selected), outfit, setting, lighting direction, colour grade, and visual continuity across all four panels. No extra panels.

CAMPAIGN GOAL
{goal_text}

SELECTED VISUAL STYLE
{style_text}

SELECTED SETTING
{environment_text}

PRODUCT REFERENCE AND CONTINUITY
{observations}
Use the uploaded original product photograph as the authoritative reference. Preserve the exact product identity, silhouette, proportions, colour, material, texture, pattern, stitching, hardware, accessories, and any original visible logo. Do not redesign, replace, beautify into a different product, invent details, or omit distinctive features. Keep the product recognisably identical in all four panels. If a feature is unclear, do not guess. If a model is selected, use an adult model and keep the same person and styling in every panel.

PANEL 1 — HOOK / HERO ESTABLISHING SHOT
Show the selected product immediately and clearly in the chosen setting. Use a compelling but natural composition, medium or three-quarter framing, clean separation from the background, and premium commercial lighting. The product must be the first thing viewers notice.

PANEL 2 — PRODUCT FORM / MAIN BENEFIT
Move to a closer medium shot that clearly shows the product's overall form, fit, silhouette, and practical use. If a model is selected, show a natural, believable interaction with the product. Avoid exaggerated poses or changes to the product.

PANEL 3 — DETAIL / TRUST SHOT
Use a close-up focused on real details visible in the reference, such as material texture, seams, fastening, handle, surface finish, or other distinctive features. Show only details that genuinely exist in the source image. Keep geometry and colours accurate.

PANEL 4 — FINAL HERO / DESIRE SHOT
Finish with the strongest polished composition of the same product in the same campaign style. Keep the product fully recognisable, well lit, and clearly visible, with balanced negative space and a natural commercial finish. This final panel should feel like a memorable closing frame.

CAMERA, LIGHTING AND ART DIRECTION
Photorealistic commercial photography, realistic anatomy and hands where applicable, natural perspective, controlled highlights, crisp product focus, tasteful depth of field, coherent colour grading, high visual quality, and deliberate framing. The four panels must feel like shots from one consistent campaign rather than four unrelated images.

STRICT NEGATIVE REQUIREMENTS
No changes to product design, colour, proportions, materials, logos, or visible details. No invented accessories or extra products. No duplicate limbs, distorted hands, warped product geometry, fake branding, watermarks, captions, subtitles, or decorative text. Panel labels or thin dividers may be used only to clarify the storyboard layout; do not add advertising copy inside the image.

OUTPUT
Return exactly one cohesive storyboard sheet with four distinct panels in a vertical 9:16 composition. Do not return a single hero image, a two-panel collage, more than four panels, or a video. The storyboard must be usable as a clear visual plan for a later product promotion."""
