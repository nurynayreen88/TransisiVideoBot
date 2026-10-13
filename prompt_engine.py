from prompt_catalog import resolve, product_hook
"""Detailed, reference-safe AI video prompt templates for KLIPPO."""

CAMERAS = {
    "orbit": "A restrained camera arc of at most 30 degrees with subtle parallax. Never reveal or fabricate an unseen side.",
    "push": "A smooth slow dolly-in from a balanced medium product shot to a crisp detail, with no digital warping.",
    "side": "A measured left-to-right lateral camera slide with gentle depth separation and stable product proportions.",
    "static": "A locked premium studio composition with delicate lighting movement and a subtle focus transition.",
}

def build_prompt(mode, product, scene, motion, style='auto', duration=10):
    duration = 20 if duration == 20 else 10
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
        "STRICT EXCLUSIONS: No dramatic spinning, flying product, aggressive morph transitions or scene changes. No invented features, extra accessories, duplicated or morphing products, "
        "changing logos or typography, people or hands, random props, floating geometry, distorted edges, "
        "flicker, jitter, abrupt exposure shifts, captions, subtitles, UI or watermarks. "
        "Do not attempt a full 360-degree rotation from one reference image."
    )
    if mode == "storyboard":
        style_key, style_name, style_template = resolve(style)
        doodle = style_key == "white_doodle"
        hook = product_hook(product)
        evidence_rules = (
            "PRODUCT EVIDENCE PRIORITY: NAMA_PRODUK is the exact printed product name only if marked legible; "
            "preserve its spelling, brand and model verbatim. TEKS_DISAHKAN and CIRI_BERTULIS are claims printed "
            "on packaging, NOT independently proven benefits: attribute them to the label if used. "
            "CIRI_VISUAL lists only features directly visible in the image. "
            "Do not replace precise visible product details with generic marketing adjectives. "
            "Use a feature callout only if it can be traced to a specific CIRI_VISUAL, a legible CIRI_BERTULIS, "
            "or explicit user-provided information consistent with the photo. "
            "If evidence is missing or uncertain, omit that callout entirely; never fill a slot with a guessed feature. "
            "Never reconstruct blurry letters or invent an exact model number. "
        )

        hook_direction = (
            "ON-SCREEN HOOK (VERIFIED CATEGORY ONLY): Display EXACTLY '" + hook + "' at the top safe area "
            "in the opening 0-2s. This wording identifies the product only and makes no unsupported benefit claim. "
            "Keep the product unobstructed; for white doodle add a small white underline and two sparkles. "
            "Do not generate any additional unverified promotional copy. If text rendering is unreliable, "
            "reserve space for accurate text overlay in editing. "
        ) if hook else (
            "NO ON-SCREEN HOOK TEXT: The product identity is not sufficiently verified. "
            "Begin with the product image and decorative white doodle only; leave out all headline text. "
            "Never guess a category, benefit, price, popularity or product name."
        )
        if doodle:
            if duration == 10:
                rules = (
                    "WHITE DOODLE 10s: 0-2s close-up with verified category hook IF AVAILABLE and two white sparkles; "
                    "2-4s full product reveal with ONE truthful short feature callout, small white icon and curved leader arrow "
                    "to a genuinely visible detail; 4-7s progressively draw a thin white dashed contour JUST OUTSIDE the "
                    "ACTUAL PRODUCT silhouette, following its left, top, right and bottom edges, NOT the frame; "
                    "hold completed contour for at least 1 second; 7-10s dotted accent, clean product hero, gentle doodle fade. "
                )
            else:
                rules = (
                    "WHITE DOODLE 20s: 0-3s close-up with verified category hook IF AVAILABLE and white sparkles; "
                    "3-7s full product reveal with up to TWO truthful concise feature callouts, tiny outlined icons "
                    "and curved leader arrows to genuinely visible details; 7-11s detail shot with dotted trail; "
                    "11-16s progressively draw a thin white dashed contour JUST OUTSIDE the ACTUAL PRODUCT silhouette "
                    "following left, top, right and bottom edges, NOT the frame, hold at least 2 seconds; "
                    "16-20s clean full-product packshot, restrained white swoosh and graceful doodle fade. "
                )
            rules += (
                "Warm authentic UGC product-ad look, thin white handwritten 2D graphics tracked to the product. "
                "No phone bezel, no invented product claims, no branding obstruction. Only verified hook (if available) and verified "
                "short feature labels may appear; reserve space for editing overlays if text rendering is unreliable. "
                "Prioritize the visible surrounding product contour over camera movement."
            )
        elif duration == 10:
            rules = (
                "STORYBOARD 10s: 0-2s product-specific Malay hook; 2-4s full-product reveal; "
                "4-7s one genuinely visible detail and tasteful style-specific emphasis; "
                "7-10s stable full-product hero closing. Coherent setting and gentle transitions."
            )
        else:
            rules = (
                "STORYBOARD 20s: 0-3s verified category hook IF AVAILABLE; 3-7s full-product reveal; "
                "7-11s one genuinely visible detail; 11-15s complementary reference-safe composition "
                "and style-specific emphasis; 15-20s stable full-product hero closing and gentle fade. "
                "No invented product angles or claims."
            )
        return (
            "KLIPPO | STORYBOARD | " + style_name + "\n"
            "OUTPUT: One cohesive vertical 9:16 product advertisement, EXACT DURATION: " + str(duration) + " seconds.\n\n"
            "PRODUCT REFERENCE: " + product + "\n\n" + identity + "\n\n"
            "STYLE FROM KLIPPO CATALOG: " + style_template + "\n\n"
            "SETTING: " + scene + "\n"
            "CAMERA: " + camera + " Stay reference-facing; never invent unseen sides.\n\n"
            + evidence_rules + "\n\n" + hook_direction + "\n\n" + rules + "\n\n"
            "CONTINUITY: Preserve exact shape, color, visible logo and count across the entire video. "
            "Use soft physically believable lighting and stable background. "
            "Do not morph the object, invent accessories or cover its visible branding. "
            "For white doodle, the graphic overlays are explicitly REQUIRED and are not captions or UI. "
            "If the video generator cannot render precise overlays, generate clean product footage and add doodles in post-production."
        )
    if mode == "storyboard":
        shots = [
            ("01 | HOOK | 0.0–1.5s", "Start with a visually arresting close crop of a genuinely visible feature. Establish the product's material and silhouette with a soft directional highlight. Camera: precise micro push-in, no sudden jump. Keep focus locked on the visible feature. End with movement that motivates the reveal."),
            ("02 | REVEAL | 1.5–3.0s", "Reveal the complete product in a carefully balanced frame. Camera: controlled pull-back within the original reference-facing view, maintaining exact scale and shape. Let the background separate naturally through restrained depth and contact shadow. Transition from the hook with matching movement and consistent lighting."),
            ("03 | CONTEXT | 3.0–5.0s", "Keep the unchanged product in the same selected setting without suggesting an unsupported function or inventing props. Show convincing surface contact, natural reflections and realistic perspective. Use a gentle camera drift to create depth while keeping the reference-facing product geometry recognizable. Transition through a subtle dissolve or match cut."),
            ("04 | DETAIL | 5.0–7.0s", "Select one authentic detail visible in the uploaded photograph: texture, finish, seam, component, packaging or label. Use a measured macro-style push, controlled depth of field and soft grazing light. Never reconstruct illegible lettering or manufacture additional details. Transition by matching the detail's position into the next hero composition."),
            ("05 | HERO | 7.0–8.5s", "Present the product as the unmistakable visual centerpiece. Camera instruction: use a restrained, reference-safe variation of the primary movement: " + camera + " Use restrained premium edge lighting, realistic material response and uncluttered negative space. The product must remain completely consistent with the reference, including its visible branding. Build visual emphasis without aggressive spinning or deformation."),
            ("06 | CLOSING | 8.5–10.0s", "Return to a clean full-product packshot with balanced framing. Slow the movement into a confident hold, then apply a subtle graceful fade. Preserve a clear product silhouette and stable highlights. Do not invent a slogan, price, call-to-action text or new logo.")
        ]
        direction = ("DIRECTOR'S SIX-SHOT STORYBOARD: Deliver one cohesive commercial using the SAME reference-facing product view throughout. Treat the six shots as framing and editing beats, not six newly generated product angles. "
                     "Keep the same product identity, spatial orientation, visual palette and believable light direction in every shot.\n\n"
                     + "\n\n".join(title + "\nVISUAL AND CAMERA BRIEF: " + detail for title, detail in shots)
                     + "\n\nEDITING AND CONTINUITY: Respect the specified timing as closely as the generator permits. "
                     "Prefer subtle reframing and no more than two soft cuts; use gentle easing. Avoid flashy templates, "
                     "random zooms and inconsistent set geometry. Every cut should advance the viewer from curiosity "
                     "to product recognition, detail appreciation and a memorable closing hero image.")
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
            "brief confident hold with an understated lighting accent. No added caption, CTA or watermark.\n\n"
            "CINEMATOGRAPHY: Premium commercial lens language, elegant motion curves, coherent depth of field, "
            "physically plausible parallax and natural material response. Maintain one consistent studio space "
            "and color grade throughout; avoid frantic motion, jump cuts, fake rotations or excessive effects."
        )
    if duration == 20:
        direction = (
            "DIRECTOR'S SINGLE-TAKE 20-SECOND BRIEF: 0-4s establish the reference-facing product in its setting; "
            "4-8s restrained camera push or lateral movement with realistic parallax; "
            "8-12s emphasize a genuinely visible detail using subtle focus and light; "
            "12-16s ease back to a complete recognizable product view with the same identity and background; "
            "16-20s elegant hero hold and gentle fade. Keep continuity, avoid new unseen angles, "
            "avoid added text or invented features. This is one coherent commercial, not a slideshow."
        )
    return (
        "KLIPPO | PROFESSIONAL IMAGE-TO-VIDEO PRODUCTION PROMPT\n"
        "OUTPUT: " + str(duration) + " seconds; portrait 9:16; high-quality realistic product commercial; "
        "one coherent deliverable; no on-screen text.\n\n"
        "PRODUCT: " + product + "\n\n" + identity + "\n\n" + art + "\n\n"
        + direction + "\n\n" + negative + "\n\n"
        "FINAL QUALITY CHECK: Consistent identity in every frame, natural physics, clean edges, "
        "stable illumination, smooth temporal coherence and polished affiliate-ad aesthetics. "
        "If the reference does not support a requested viewpoint, use a safe crop or modest "
        "2D camera movement instead of hallucinating the product."
    )
