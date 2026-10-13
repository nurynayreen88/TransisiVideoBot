"""Versioned, additive local SQLite catalog of storyboard prompt styles."""
import os
import hashlib
import re
import random
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("KLIPPO_PROMPT_DB", str(Path(__file__).with_name("prompt_catalog.sqlite3"))))
STYLES = {
    "white_doodle": ("✏️ White Doodle", "Reference-style warm UGC product advertisement with product-specific Malay hook, small white handwritten feature callouts, outlined icons, curved leader arrows, tiny sparkle doodles, and a later animated white dashed contour tracing around the actual product silhouette. Show product/detail/hero compositions with realistic continuity. Graphics are flat tracked 2D overlays; keep branding visible. Never invent claims or recreate the phone bezel from the reference video."),
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

# Keyword-to-hook mappings are deterministic templates, not an additional AI request.
HOOKS = {
    "lampu": (("lampu", "light", "lighting", "lantern"), ("SUDUT INI NAMPAK BERBEZA!", "TENGOK REKAAN LAMPU INI!")),
    "beg": (("beg", "bag", "handbag", "backpack", "purse"), ("DETAIL BEG INI MENARIK!", "JOM TENGOK BEG INI!")),
    "kasut": (("kasut", "shoe", "sneaker", "sandal"), ("TENGOK GAYA KASUT INI!", "DETAIL KASUT INI MENARIK!")),
    "botol": (("botol", "bottle", "tumbler", "flask"), ("BOTOL INI CURI PERHATIAN!", "TENGOK REKAAN BOTOL INI!")),
    "jam": (("jam", "watch", "clock"), ("DETAIL JAM INI MENARIK!", "JOM TENGOK JAM INI!")),
    "kerusi": (("kerusi", "chair", "sofa"), ("TENGOK REKAAN INI!", "SUDUT RUANG NAMPAK BERBEZA!")),
    "meja": (("meja", "table", "desk"), ("JOM TENGOK REKAAN MEJA!", "DETAIL MEJA INI MENARIK!")),
    "telefon": (("telefon", "phone", "smartphone"), ("TENGOK AKSESORI INI!", "DETAIL PRODUK INI MENARIK!")),
    "kipas": (("kipas", "fan"), ("TENGOK REKAAN KIPAS INI!", "DETAIL KIPAS INI MENARIK!")),
    "katil": (("katil", "mattress", "bed"), ("TENGOK REKAAN INI!", "IDEA UNTUK RUANG ANDA!")),
    "pakaian": (("baju", "shirt", "dress", "clothing", "jacket"), ("DETAIL PAKAIAN INI MENARIK!", "JOM TENGOK GAYA INI!")),
    "alat_dapur": (("dapur", "kitchen", "pan", "pot", "blender"), ("JOM TENGOK ITEM DAPUR INI!", "DETAIL PRODUK DAPUR INI!")),
}
HOOK_SCHEMA = """CREATE TABLE IF NOT EXISTS storyboard_hooks (
    category TEXT PRIMARY KEY, keywords TEXT NOT NULL, hooks TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1
)"""

def product_hook(description):
    import json
    with connect() as db:
        db.execute(HOOK_SCHEMA)
        db.executemany(
            "INSERT OR IGNORE INTO storyboard_hooks(category, keywords, hooks) VALUES (?, ?, ?)",
            [(category, json.dumps(keywords), json.dumps(hooks)) for category, (keywords, hooks) in HOOKS.items()]
        )
        db.commit()
        rows = db.execute("SELECT keywords, hooks FROM storyboard_hooks WHERE active=1 ORDER BY rowid").fetchall()
    words = set(re.findall(r"[a-zA-ZÀ-ÿ]+", (description or "").lower()))
    options = None
    for keywords, hooks in rows:
        if words.intersection(json.loads(keywords)):
            options = json.loads(hooks)
            break
    if not options:
        options = ["TENGOK DETAIL PRODUK INI!", "REKAAN INI CURI PERHATIAN!", "JOM LIHAT LEBIH DEKAT!"]
    digest = hashlib.sha256((description or "").encode("utf-8")).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]
