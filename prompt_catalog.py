"""Versioned, additive local SQLite catalog of storyboard prompt styles."""
import os
import hashlib
import re
import random
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("KLIPPO_PROMPT_DB", str(Path(__file__).with_name("prompt_catalog.sqlite3"))))
STYLES = {
    "white_doodle": ("✏️ White Doodle", """UNIVERSAL WHITE DOODLE STYLE — suitable for any product category. Treat the user's supplied product image(s) as the visual source of truth whenever provided; use written product details only as supporting context. First reveal the complete, unchanged product. Draw thin white handwritten 2D linework progressively around only the visible silhouette and verified details: adapt the drawing to the object's actual outline and structure, whether it is clothing, a bag, footwear, cosmetics, food, electronics, home goods, accessories, tools or another product. Use one or two small arrows or sparkles only when they point to a genuinely visible detail; never cover the product, readable branding or important features. Keep product geometry, colors, labels, quantities, proportions and visible parts consistent. Part 1: clean reveal, one verified detail, restrained doodle accent, then hold a stable full-product frame for the Part 2 handoff; do not complete the main surrounding contour yet. Part 2: resume from the same framing, progressively trace a thin white dashed contour around the actual visible silhouette, hold briefly, then return to a clean full-product hero finish. Graphics are flat 2D overlays, not physical objects, captions or UI. Do not invent unseen sides, features, materials, accessories, claims, prices, popularity or text. Never guess a category, benefit, price, popularity or product name. Do not force a product-specific action that the reference does not support."""),
    "cinematic": ("🎬 Cinematic Premium", "Premium realistic commercial: soft key light, restrained highlights, natural shadows, slow camera push, consistent product and environment."),
    "minimal": ("✨ Minimal Motion Graphic", "Bright uncluttered product framing, subtle geometric accent lines and smooth minimal graphic reveals, elegant spacing and gentle motion."),
    "dynamic": ("⚡ Dynamic Affiliate", "Engaging but controlled affiliate pacing: striking opening crop, feature emphasis with clean graphic accents, smooth match cuts and clear final hero shot."),
    "luxury": ("💎 Luxury Product", "Refined dark or neutral luxury lighting, soft rim highlights, rich material texture, sophisticated slow movement, elegant product-focused closing."),
    "mirror_selfie": ("📱 Mirror Selfie", "Authentic handheld smartphone mirror-selfie aesthetic. Use a consistent person, outfit, mirror viewpoint, phone and room throughout the shot. Use only small natural movements such as a gentle posture shift or slight phone adjustment; no outfit changes, exaggerated posing or invented people."),
    "lifestyle": ("🌿 Everyday Lifestyle", "Natural candid lifestyle commercial in a believable everyday setting that suits the visible product. Soft daylight, relaxed human pacing, realistic contact and subtle camera drift. Do not invent product functions, extra accessories or unnecessary people."),
    "ugc_review": ("🗣️ UGC Creator Review", "Friendly creator-style product demonstration with authentic phone-camera framing and natural room light. Focus on showing the exact visible item and one or two real visible details; gestures stay simple and plausible. No fabricated testimonials, claims, ratings, prices or spoken words unless explicitly supplied."),
    "fashion_editorial": ("👗 Fashion Editorial", "Polished fashion-campaign framing with confident but natural posing, tasteful full-length and detail compositions, soft directional light and refined color grading. Preserve the exact garment, pattern placement, fit, accessories and visible person; no wardrobe changes or invented garment details."),
    "beauty_macro": ("✨ Beauty & Macro Detail", "Elegant beauty-ad close-ups with controlled highlights, shallow but purposeful depth of field and slow macro-style camera movement. Reveal only generic texture, finish, packaging and details supported by the product name; keep unknown materials neutral. Keep labels accurate and never invent cosmetic results or health claims."),
    "food_appetite": ("🍓 Food & Drink Hero", "Fresh appetizing food-commercial styling with soft directional light, realistic texture and a carefully composed hero shot. Use gentle camera movement and natural-looking steam or condensation only when physically plausible and supported by the product. Do not add ingredients, toppings, servings or packaging that are not shown."),
    "tech_demo": ("⚙️ Tech Product Demo", "Clean modern technology advertisement with precise framing, controlled reflections and measured camera slides. Highlight only ports, buttons, screens and components actually visible. Keep screen content unchanged unless the user supplies exact content; no fake interfaces, extra accessories or impossible device transformations."),
    "cozy_home": ("🏡 Cozy Home & Living", "Warm inviting home-commercial atmosphere with natural window light, soft shadows and a lived-in but uncluttered setting. Keep the product as the clear hero and use believable spatial scale and contact shadows. Do not add furniture, functions or accessories that imply unprovided product features."),
    "flatlay": ("🧺 Clean Flat Lay", "Tasteful top-down or slightly angled flat-lay presentation with balanced spacing, restrained props and a coordinated background. Keep the named product's presentation consistent in shape, color and orientation; props must remain secondary and must never imply they are included with the product."),
    "unboxing": ("🎁 Unboxing Reveal", "A satisfying, measured reveal focused on the exact visible product and its actual packaging. Use simple, natural hand interaction only when appropriate to the product; avoid inventing box contents, seals, accessories or extra items. Finish with a clean hero composition."),
    "playful_viral": ("🎨 Playful & Viral", "Bright, upbeat short-form ad energy with a strong visual opening, playful but physically plausible camera movement and a memorable clean hero finish. Keep effects restrained and product identity stable; no chaotic transitions, misleading transformations, invented claims or excessive graphics."),
    "nature_fresh": ("🌱 Fresh & Natural", "Airy natural-light product film with organic colors, soft sunlight and subtle background movement such as a gentle breeze only where appropriate. Keep the product sharply recognizable and grounded; never imply ingredients, eco-certifications or natural benefits that are not explicitly verified."),
    "studio_360_safe": ("🔍 Studio Detail Showcase", "Professional neutral-studio showcase using front-facing framing, gentle reframing and close-ups of visible details. Create the impression of multiple viewpoints through safe crops and camera movement, not a fabricated 360-degree rotation or unseen product surfaces."),
    "fast_cut": ("⚡ Trendy Fast-Cut", "Energetic short-form commercial rhythm using two or three clean match cuts or reframings, a striking opening composition and a clear final hero frame. Each cut must be physically plausible and the product identity must remain identical."),
    "pov_demo": ("👁️ POV / First Person", "First-person product interaction with a stable natural viewpoint and one simple action appropriate to the visible item. Avoid invented hands, extra items and unseen product angles; maintain realistic scale and movement."),
    "funny_ad": ("🎭 Funny Commercial", "Light, family-friendly visual humor built around one simple harmless situational beat, then return attention to the product. Keep actions physically plausible; do not distort, damage or transform the product."),
    "reaction_hook": ("😍 Reaction & Wow Factor", "Open with a believable moment of interest or pleasant surprise if a person is visible, then reveal the exact product and one genuinely visible detail. Avoid exaggerated acting, fake testimonials, unsupported claims or distracting gestures."),
    "golden_hour": ("🌇 Golden-Hour Editorial", "Fashion-editorial composition in warm natural golden-hour light, refined color grading and gentle camera movement. Keep the stated outfit, product, person and selected environment consistent; no wardrobe changes or fabricated details."),
    "creative_reveal": ("✨ Creative Reveal", "Build a memorable reveal using lighting, focus, framing or a smooth camera transition rather than changing the object itself. The product must remain identical: no morphing, teleportation, recoloring or impossible transformation."),
    "handbag_showcase": ("👜 Handbag Hero Reveal", "Premium handbag commercial with a clean hero reveal, graceful camera push, balanced front or three-quarter framing and a polished closing hold. Keep handles and straps plausible; do not invent material, branding or hardware."),
    "bag_detail_macro": ("🔎 Bag Detail Close-Up", "Slow detail-led commercial focusing on the bag silhouette and only generic visible areas such as seams, handles, edges or closure when appropriate. Do not assert material, compartments or features absent from the product name."),
    "bag_flatlay": ("🧺 Bag Editorial Flat Lay", "Refined overhead or three-quarter flat lay with the bag as the unmistakable hero, generous negative space, soft shadows and a gentle camera drift. Avoid props that imply included accessories."),
    "bag_daily_carry": ("🌿 Everyday Bag Lifestyle", "Believable everyday setting with a natural, relaxed presentation of the named bag. Keep carrying posture and strap placement physically plausible; make no capacity or durability claims."),
    "bag_tabletop_reveal": ("✨ Tabletop Bag Reveal", "A controlled tabletop hero reveal using a gentle light change, a slow camera push and a stable final frame. Keep the bag's construction generic where the name gives no detail."),
    "sling_bag_lifestyle": ("🎒 Sling / Crossbody Lifestyle", "Lifestyle showcase for a sling or crossbody bag, with a natural crossbody carrying pose or a clean tabletop alternative. Keep strap placement realistic and do not invent pockets or capacity."),
    "backpack_demo": ("🎒 Backpack Ready-to-Go", "Show the named backpack upright in a tidy everyday setting, using a slow camera move and a clean hero finish. Do not invent compartments, laptop sleeves, water resistance or included accessories."),
    "wallet_luxury_macro": ("👛 Luxury Wallet Macro", "Premium wallet close-up with soft directional light, restrained reflections and a slow macro-style camera move. Do not assume leather, exact stitching, closure type or interior layout."),
    "wallet_open_close": ("👛 Wallet Open & Close", "A simple, plausible opening-and-closing presentation of the named wallet. Keep the interior neutral; do not invent card slots, coin pockets, compartments or capacity."),
    "wallet_daily_carry": ("🧥 Everyday Wallet", "Natural everyday-carry scene focused on the wallet itself, with a calm hand interaction or a tidy tabletop presentation. No capacity, durability or security claims."),
    "wallet_flatlay": ("🧾 Clean Wallet Flat Lay", "Minimal overhead flat lay with the wallet as the hero, soft contact shadow and careful spacing. Do not add cards, cash or accessories unless explicitly included in the product name."),
    "wallet_gift_reveal": ("🎁 Gift-Style Wallet Reveal", "Tasteful gift-inspired reveal with neutral wrapping-like styling kept separate from the product. Do not imply that a gift box or packaging is included."),
}
SCHEMA = """CREATE TABLE IF NOT EXISTS storyboard_prompt_styles (
    style_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    template TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1
)"""

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    db.execute(SCHEMA)
    # Seed missing styles only: preserve any previously edited or added rows.
    db.executemany("INSERT OR IGNORE INTO storyboard_prompt_styles(style_key, display_name, template) VALUES (?, ?, ?)",
                   [(k, *v) for k, v in STYLES.items()])
    # Upgrade only the original bundled doodle seed, never a user-customized row.
    old_doodle = "Animated thin white hand-drawn arrows, dotted paths, sparkle stars, and feature circles. Every stroke visibly draws itself over time as a flat 2D overlay; no visible pen, no invented text."
    db.execute(
        "UPDATE storyboard_prompt_styles SET template=?, version=2 WHERE style_key='white_doodle' AND version=1 AND template=?",
        (STYLES["white_doodle"][1], old_doodle)
    )
    # Migrate only untouched v2 seed; preserve user-edited templates.
    prior_v2 = "MANDATORY HERO EFFECT: a continuous animated white hand-drawn contour/halo must wrap AROUND THE ENTIRE OUTER SILHOUETTE of the visible product, not merely decorate the empty background. Follow the real 2D outline with a narrow consistent 3-6% product-width gap; begin at lower left, travel up the left edge, across the top, down the right edge and curve under the base to nearly close the loop. Make the line visibly draw on progressively and remain readable for at least 2 seconds. This is a flat composited overlay, not a physical ring, not an oval over the center, not a line crossing the product. Secondary thin white dotted trails, curved feature arrow and 2-3 tiny sparkle stars may appear OUTSIDE the contour. Do not add a visible pen, invented text or random disconnected decoration."
    db.execute("UPDATE storyboard_prompt_styles SET template=?, version=3 WHERE style_key='white_doodle' AND version=2 AND template=?",
               (STYLES["white_doodle"][1], prior_v2))
    # Upgrade only the unchanged bundled v3 seed to the refined evidence-first template.
    previous_v3 = "Reference-style warm UGC product advertisement with product-specific Malay hook, small white handwritten feature callouts, outlined icons, curved leader arrows, tiny sparkle doodles, and a later animated white dashed contour tracing around the actual product silhouette. Show product/detail/hero compositions with realistic continuity. Graphics are flat tracked 2D overlays; keep branding visible. Never invent claims or recreate the phone bezel from the reference video."
    db.execute(
        "UPDATE storyboard_prompt_styles SET template=?, version=4 WHERE style_key='white_doodle' AND version=3 AND template=?",
        (STYLES["white_doodle"][1], previous_v3)
    )
    # A v2-to-v3 migration above uses the current seed; normalize that exact row to v4.
    db.execute(
        "UPDATE storyboard_prompt_styles SET version=4 WHERE style_key='white_doodle' AND version=3 AND template=?",
        (STYLES["white_doodle"][1],)
    )
    # Fresh databases seed the current template at the default version; mark that exact seed as v4.
    db.execute(
        "UPDATE storyboard_prompt_styles SET version=4 WHERE style_key='white_doodle' AND version=1 AND template=?",
        (STYLES["white_doodle"][1],)
    )
    # Upgrade only the unchanged v4 bundled seed; leave user-customized rows untouched.
    previous_v4 = """Text-only product storyboard based on the user-provided product name and optional written details. Use a verified product-name category hook only when clear; omit unsupported labels. Add at most two short neutral labels only when explicitly supported by the supplied text. Use thin white handwritten 2D doodles, tiny sparkles and simple arrows without obscuring the product. Start with a clean hero reveal, show a plausible generic detail, then settle on a stable full-product frame and HOLD the final frame. Do not draw the main surrounding contour in Part 1. In Part 2, continue from the held framing and progressively trace a thin white dashed contour around the product silhouette, then hold it briefly before a clean hero finish. All doodles are flat 2D overlays, never captions or UI. No uploaded image or AI image analysis is used. Never invent unseen sides, product features, accessories, claims, prices, popularity or unprovided text; Never invent unseen sides."""
    db.execute(
        "UPDATE storyboard_prompt_styles SET template=?, version=5 WHERE style_key='white_doodle' AND version=4 AND template=?",
        (STYLES["white_doodle"][1], previous_v4)
    )
    # Fresh databases and untouched older bundled seeds now use the current v5 template.
    db.execute(
        "UPDATE storyboard_prompt_styles SET version=5 WHERE style_key='white_doodle' AND version=4 AND template=?",
        (STYLES["white_doodle"][1],)
    )
    db.commit()
    return db

def choices():
    with connect() as db:
        return db.execute("SELECT style_key, display_name FROM storyboard_prompt_styles WHERE active=1 ORDER BY rowid").fetchall()

def resolve(key):
    with connect() as db:
        if key == "auto":
            rows = db.execute("SELECT style_key, display_name, template FROM storyboard_prompt_styles WHERE active=1 ORDER BY style_key").fetchall()
            if not rows:
                raise ValueError("No active storyboard styles")
            return random.choice(rows)
        row = db.execute("SELECT style_key, display_name, template FROM storyboard_prompt_styles WHERE style_key=? AND active=1", (key,)).fetchone()
        if row is None:
            raise ValueError("Unknown storyboard style")
        return row

# Conservative category hooks: product identity only, never invented benefits or hype.
HOOKS = {
    "lampu": (("lampu", "lantern", "lighting"), ("TENGOK LAMPU INI",)),
    "beg": (("beg", "bag", "handbag", "backpack", "purse"), ("TENGOK BEG INI",)),
    "kasut": (("kasut", "shoe", "sneaker", "sandal"), ("TENGOK KASUT INI",)),
    "botol": (("botol", "bottle", "tumbler", "flask"), ("TENGOK BOTOL INI",)),
    "jam": (("jam", "watch", "clock"), ("TENGOK JAM INI",)),
    "kerusi": (("kerusi", "chair", "sofa"), ("TENGOK KERUSI INI",)),
    "meja": (("meja", "table", "desk"), ("TENGOK MEJA INI",)),
    "telefon": (("telefon", "phone", "smartphone"), ("TENGOK TELEFON INI",)),
    "kipas": (("kipas", "fan"), ("TENGOK KIPAS INI",)),
    "katil": (("katil", "mattress", "bed"), ("TENGOK PRODUK INI",)),
    "pakaian": (("baju", "shirt", "dress", "clothing", "jacket"), ("TENGOK PAKAIAN INI",)),
    "alat_dapur": (("dapur", "kitchen", "pan", "pot", "blender"), ("TENGOK PRODUK DAPUR INI",)),
}
HOOK_SCHEMA = """CREATE TABLE IF NOT EXISTS storyboard_hooks (
    category TEXT PRIMARY KEY, keywords TEXT NOT NULL, hooks TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1
)"""

def product_hook(description):
    """Return a conservative category hook or None if product identity is unclear."""
    import json
    with connect() as db:
        db.execute(HOOK_SCHEMA)
        db.executemany(
            "INSERT OR IGNORE INTO storyboard_hooks(category, keywords, hooks) VALUES (?, ?, ?)",
            [(category, json.dumps(keywords), json.dumps(hooks)) for category, (keywords, hooks) in HOOKS.items()]
        )
        # Only migrate untouched old stock rows; preserve user-customized database entries.
        old = {
            "lampu": ("SUDUT INI NAMPAK BERBEZA!", "TENGOK REKAAN LAMPU INI!"),
            "beg": ("DETAIL BEG INI MENARIK!", "JOM TENGOK BEG INI!"),
            "kasut": ("TENGOK GAYA KASUT INI!", "DETAIL KASUT INI MENARIK!"),
            "botol": ("BOTOL INI CURI PERHATIAN!", "TENGOK REKAAN BOTOL INI!"),
            "jam": ("DETAIL JAM INI MENARIK!", "JOM TENGOK JAM INI!"),
            "kerusi": ("TENGOK REKAAN INI!", "SUDUT RUANG NAMPAK BERBEZA!"),
            "meja": ("JOM TENGOK REKAAN MEJA!", "DETAIL MEJA INI MENARIK!"),
            "telefon": ("TENGOK AKSESORI INI!", "DETAIL PRODUK INI MENARIK!"),
            "kipas": ("TENGOK REKAAN KIPAS INI!", "DETAIL KIPAS INI MENARIK!"),
            "katil": ("TENGOK REKAAN INI!", "IDEA UNTUK RUANG ANDA!"),
            "pakaian": ("DETAIL PAKAIAN INI MENARIK!", "JOM TENGOK GAYA INI!"),
            "alat_dapur": ("JOM TENGOK ITEM DAPUR INI!", "DETAIL PRODUK DAPUR INI!"),
        }
        for category, (_, hooks) in HOOKS.items():
            db.execute(
                "UPDATE storyboard_hooks SET hooks=?, version=2 WHERE category=? AND version=1 AND hooks=?",
                (json.dumps(hooks), category, json.dumps(old[category]))
            )
        db.commit()
        rows = db.execute("SELECT keywords, hooks FROM storyboard_hooks WHERE active=1 ORDER BY rowid").fetchall()
    description = description or ""
    name_match = re.search(r"(?im)^NAMA_PRODUK:\s*(.+)$", description)
    if name_match:
        name = name_match.group(1).strip()
        if name and name.upper() not in ("TIDAK PASTI", "TIADA", "TIDAK DAPAT DIPASTIKAN", "UNKNOWN", "NONE"):
            # Exact observed printed name: never generate a speculative product claim.
            return "KENALI " + name
    category_match = re.search(r"(?im)^KATEGORI:\s*(.+)$", description)
    if not category_match:
        return None
    category = category_match.group(1).strip()
    if not category or category.upper() in ("TIDAK PASTI", "TIADA", "UNKNOWN", "NONE"):
        return None
    words = set(re.findall(r"[a-zA-ZÀ-ÿ]+", category.lower()))
    matches = []
    for keywords, hooks in rows:
        if words.intersection(json.loads(keywords)):
            matches.append(json.loads(hooks))
    if len(matches) != 1 or not matches[0]:
        return None
    return matches[0][0]
