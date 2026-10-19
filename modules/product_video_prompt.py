"""Copy-ready 10-second-segment product video prompts with realistic scale and Malaysian Malay audio."""

DURATION_SEGMENTS = {10: 1, 20: 2, 30: 3}

CAMPAIGN_STAGES = {
    10: [
        ("HOOK + HERO", "Open immediately with a product-specific visual hook. Show the real product clearly, demonstrate one key visible feature or use, then finish with a brief, natural call to action. Do not cram multiple claims into this short clip.")
    ],
    20: [
        ("HOOK + INTRODUCTION", "Create curiosity with a product-specific visual hook and establish the product or the everyday situation it addresses. End with an action or camera position that can continue naturally into the next clip. Do not deliver the final CTA yet."),
        ("DEMONSTRATION + CTA", "Continue naturally from the previous clip. Demonstrate one realistic use or visible benefit, then finish with a concise, friendly call to action. Do not repeat the opening hook.")
    ],
    30: [
        ("HOOK + SITUATION", "Start with a distinctive, product-specific hook and a relatable situation. Introduce the product clearly, but save the full demonstration and final CTA for later clips."),
        ("DEMONSTRATION + BENEFIT", "Continue the same scene or action. Demonstrate how the product is used and highlight one or two benefits supported by the reference image or user-provided facts. Do not repeat the hook or deliver the final CTA yet."),
        ("DETAIL + CTA", "Continue the story with a fresh close-up or useful product detail, then close with a clear, short call to action. Do not invent specifications, discounts, guarantees, or performance claims.")
    ],
}


def build_video_prompts(duration, campaign="Shopee affiliate"):
    """Return one independent prompt per 10 seconds, with progression by total duration."""
    if duration not in DURATION_SEGMENTS:
        raise ValueError("Duration must be 10, 20, or 30 seconds.")
    stages = CAMPAIGN_STAGES[duration]
    prompts = []
    for index, (stage_name, stage_direction) in enumerate(stages, start=1):
        continuity = (
            "This is the first clip. Establish the visual identity and product position clearly."
            if index == 1 else
            "This is a continuation of the immediately preceding 10-second clip. Match the exact product, "
            "its size and geometry, character identity, clothing, voice, lighting, colour grade, location, "
            "and camera direction. Begin from a plausible continuation, not a fresh unrelated opening."
        )
        if index == len(stages):
            continuity += " This is the final clip; finish the story decisively."
        prompts.append(f"""KLIPPO — {duration}-SECOND VIDEO / CLIP {index} OF {len(stages)}
CLIP LENGTH: exactly 10 seconds. Generate this clip only; do not summarise or combine other clips.
CAMPAIGN: {campaign}
STORY STAGE: {stage_name}

VISUAL DIRECTION (English):
Create one photorealistic 9:16 vertical commercial clip. Use the uploaded product photo as the authoritative reference. Preserve its exact identity, design, silhouette, colour, surface, material appearance, stones, settings, labels, accessories and visible details. Keep the product recognisably the same throughout. {continuity}

REAL-WORLD SCALE — CRITICAL:
Maintain physically believable real-world dimensions and proportions relative to hands, fingers, wrists, people, furniture and the environment. Never enlarge the physical product to create a close-up; use macro framing and camera movement instead. A ring must remain small enough to fit naturally on a human finger and must never become table-sized. A watch must fit a wrist; a phone must fit a hand; cosmetics and appliances must have category-appropriate dimensions. Keep scale consistent in every shot. No giant product, warped geometry, melted shape, duplicated items, floating objects, or impossible hand interaction. If the exact dimensions are unknown, choose ordinary realistic proportions for this product category rather than exaggerating.

CATEGORY-SPECIFIC SCENE AND ACTION LOGIC:
First infer the actual product category from the reference image, then choose only actions and surroundings that fit that category. Jewellery and rings stay wearable and finger-sized; use macro camera framing for close-ups. Electronics remain handheld or correctly placed, with no invented screen content, buttons or ports. Appliances and kitchenware belong on safe, realistic work surfaces and must not perform unsafe or unsupported functions. Beauty products may show only visible packaging, cap, applicator or texture; never imply ingredients or results. Clothing must fit naturally on an adult model with unchanged cut, colour and drape. Bags and wallets use only existing handles, straps and visible closures; do not invent pockets or compartments. Shoes remain grounded at real footwear scale. Food uses realistic serving sizes with no added ingredients or toppings. Furniture and home products must fit their rooms and surroundings. Stationery uses blank paper or abstract marks only, never readable generated writing. Sports actions must be safe and plausible. Travel items keep realistic luggage dimensions. Pet and baby products must be shown in calm, safe situations. Automotive products appear in a stationary vehicle or safe work setting. Gardening actions must respect real contact with plants, soil and water. Never force an unboxing, model, hand interaction or extra prop when it does not suit the product.

SHOT AND STORY:
{stage_direction}
Use physically plausible motion, natural hands/anatomy, stable geometry, coherent perspective, clear product focus, realistic shadows and premium but believable lighting. Avoid frantic cuts and excessive camera motion. No unsupported claims or invented product specifications.

VOICE AND LANGUAGE — MANDATORY:
If spoken dialogue or voiceover is present, it MUST be natural Bahasa Melayu Malaysia, delivered by a native-sounding Malaysian Malay speaker with Malaysian pronunciation, vocabulary, rhythm and intonation. Indonesian voice, Indonesian accent, Indonesian vocabulary and machine-translated phrasing are prohibited. Avoid Indonesian words such as "banget", "nggak" and "kalian"; use natural Malaysian alternatives suited to the tone. Use a {("short, attention-grabbing" if index == 1 else "concise, conversational")} line that can genuinely be spoken within this 10-second clip at a natural pace. Keep dialogue brief (normally no more than about 18–22 Malay words per clip), product-specific, and non-repetitive. Use the same speaker identity and Malaysian accent across all connected clips. Background music may support the mood but must remain quieter than the voice.

NO ON-SCREEN TEXT:
No subtitles, captions, written advertising copy, added labels, logos, watermarks, or UI overlays. Preserve only branding/text that already exists on the actual product in the reference image. Do not generate extra text anywhere in the scene.

CLIP-SPECIFIC PROGRESSION:
Respect this clip's distinct story stage described above; do not restate the same direction in a second checklist. Do not repeat another clip's hook, demonstration, dialogue, or CTA. End on a visually coherent moment that supports continuity.""")
    return prompts
