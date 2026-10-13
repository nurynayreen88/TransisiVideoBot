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
        shots = [
            ("01 | HOOK | 0.0–1.5s", "Start with a visually arresting close crop of a genuinely visible feature. Establish the product's material and silhouette with a soft directional highlight. Camera: precise micro push-in, no sudden jump. Keep focus locked on the visible feature. End with movement that motivates the reveal."),
            ("02 | REVEAL | 1.5–3.0s", "Reveal the complete product in a carefully balanced frame. Camera: slow lateral slide or controlled pull-back, maintaining exact scale and shape. Let the background separate naturally through restrained depth and contact shadow. Transition from the hook with matching movement and consistent lighting."),
            ("03 | CONTEXT | 3.0–5.0s", "Place the unchanged product in the selected setting without suggesting an unsupported function or inventing props. Show convincing surface contact, natural reflections and realistic perspective. Use a gentle camera drift to create depth while keeping the reference-facing product geometry recognizable. Transition through a subtle dissolve or match cut."),
            ("04 | DETAIL | 5.0–7.0s", "Select one authentic detail visible in the uploaded photograph: texture, finish, seam, component, packaging or label. Use a measured macro-style push, controlled depth of field and soft grazing light. Never reconstruct illegible lettering or manufacture additional details. Transition by matching the detail's position into the next hero composition."),
            ("05 | HERO | 7.0–8.5s", "Present the product as the unmistakable visual centerpiece. Camera instruction: " + camera + " Use restrained premium edge lighting, realistic material response and uncluttered negative space. The product must remain completely consistent with the reference, including its visible branding. Build visual emphasis without aggressive spinning or deformation."),
            ("06 | CLOSING | 8.5–10.0s", "Return to a clean full-product packshot with balanced framing. Slow the movement into a confident hold, then apply a subtle graceful fade. Preserve a clear product silhouette and stable highlights. Do not invent a slogan, price, call-to-action text or new logo.")
        ]
        direction = ("DIRECTOR'S SIX-SHOT STORYBOARD: Deliver a SINGLE cohesive commercial, not six separate videos. "
                     "Keep the same product identity, spatial orientation, visual palette and believable light direction in every shot.\\n\\n"
                     + "\\n\\n".join(title + "\\nVISUAL AND CAMERA BRIEF: " + detail for title, detail in shots)
                     + "\\n\\nEDITING AND CONTINUITY: Respect the specified timing as closely as the generator permits. "
                     "Use purposeful motion-matched cuts, restrained dissolves and gentle easing. Avoid flashy templates, "
                     "random zooms and inconsistent set geometry. Every cut should advance the viewer from curiosity "
                     "to product recognition, detail appreciation and a memorable closing hero image.")
    else:
        direction = (
            "DIRECTOR'S SINGLE-TAKE BRIEF: Create one sophisticated uninterrupted 10-second commercial, "
            "not a slideshow, montage or set of disconnected AI shots. The visual story progresses from "
            "anticipation to discovery and finally a confident product hero moment.\\n\\n"
            "0.0–2.0s | OPENING: Begin with a deliberately composed medium-wide shot. Establish the selected "
            "environment with natural perspective, restrained highlights and believable grounding. Introduce "
            "the product using a delicate light reveal rather than sudden object appearance. Keep its visible "
            "branding and outline stable from the first frame.\\n\\n"
            "2.0–5.0s | DEVELOPMENT: Start the requested camera move with gradual acceleration: " + camera +
            " Build depth through the background and lighting rather than bending or reconstructing the object. "
            "Hold a clean focal plane on the product. Show only surfaces genuinely supported by the reference.\\n\\n"
            "5.0–7.5s | VISUAL EMPHASIS: Refine the composition around a visible material, finish or design detail. "
            "Use subtle controlled light falloff and accurate reflections. Preserve the exact packaging and "
            "typography, without enhancing unreadable text into invented words. Keep movement continuous and natural.\\n\\n"
            "7.5–10.0s | HERO FINISH: Ease the camera into a balanced full-product composition. Let the product "
            "remain clearly legible, with polished edge separation and a stable contact shadow. Finish on a "
            "brief confident hold with an understated lighting accent. No added caption, CTA or watermark.\\n\\n"
            "CINEMATOGRAPHY: Premium commercial lens language, elegant motion curves, coherent depth of field, "
            "physically plausible parallax and natural material response. Maintain one consistent studio space "
            "and color grade throughout; avoid frantic motion, jump cuts, fake rotations or excessive effects."
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
