"""Versioned, additive local SQLite catalog of storyboard prompt styles."""
import os
import random
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("KLIPPO_PROMPT_DB", str(Path(__file__).with_name("prompt_catalog.sqlite3"))))
STYLES = {
    "white_doodle": ("✏️ White Doodle", "Animated thin white hand-drawn arrows, dotted paths, sparkle stars, and feature circles. Every stroke visibly draws itself over time as a flat 2D overlay; no visible pen, no invented text."),
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
