"""Versioned, additive local SQLite catalog of storyboard prompt styles."""
import os
import hashlib
import re
import random
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("KLIPPO_PROMPT_DB", str(Path(__file__).with_name("prompt_catalog.sqlite3"))))
STYLES = {
    "white_doodle": ("✏️ White Doodle", """Warm, authentic UGC product advertisement with a clean premium background chosen to complement the uploaded reference. Use thin white handwritten 2D doodles tracked to the actual product: tiny sparkles, small outlined icons, short factual feature callouts and curved leader arrows. Use a product-name or Malay category hook only when product identity is verified; if uncertain, show no headline text. Add at most two short feature labels, each supported by a clearly visible feature, legible packaging text, or consistent user-provided detail; omit unsupported labels rather than guessing. Start with a close-up, reveal the complete product, show one reference-supported detail, then settle on a stable full-product frame and HOLD the final frame for Part 2. Do not draw the main surrounding contour in Part 1. In Part 2, continue from the held frame and progressively trace a thin white dashed contour just outside the actual visible product silhouette, then hold it briefly before a clean hero finish. All doodles are flat tracked overlays, never obscure visible branding, and never become captions or UI. Preserve exact silhouette, proportions, visible color, material, count, orientation, packaging, labels and logos. Never invent unseen sides, product features, accessories, claims, prices, popularity, or unreadable text; never recreate a phone bezel from a reference video. If accurate overlay rendering is unreliable, output clean reference-locked footage for doodles to be added in post-production."""),

    "cinematic": ("🎬 Cinematic Premium", "Premium realistic commercial: soft key light, restrained highlights, natural shadows, slow camera push, consistent product and environment."),
    "minimal": ("✨ Minimal Motion Graphic", "Bright uncluttered product framing, subtle geometric accent lines and smooth minimal graphic reveals, elegant spacing and gentle motion."),
    "dynamic": ("⚡ Dynamic Affiliate", "Engaging but controlled affiliate pacing: striking opening crop, feature emphasis with clean graphic accents, smooth match cuts and clear final hero shot."),
    "luxury": ("💎 Luxury Product", "Refined dark or neutral luxury lighting, soft rim highlights, rich material texture, sophisticated slow movement, elegant product-focused closing."),
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
