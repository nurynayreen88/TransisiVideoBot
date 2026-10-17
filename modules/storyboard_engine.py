"""Single-image storyboard generation with an explicit Gemini API cost gate.

Image generation is disabled by default. To opt in, set
KLIPPO_ENABLE_GEMINI_IMAGE_API=true and GEMINI_STORYBOARD_IMAGE_MODEL to a
model enabled for the project's Gemini API key. Google AI Plan app access does
not itself imply free API access.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image, ImageOps


class StoryboardEngineError(RuntimeError):
    """Safe, user-facing error from the storyboard engine."""


STYLE_LABELS = {
    "product_only": "A product-only hero shot; no people, hands, or extra products.",
    "model_holding": "A realistic model naturally holding or wearing the exact product.",
    "model_lifestyle": "A realistic lifestyle scene featuring a model with the exact product.",
}
ENVIRONMENT_LABELS = {
    "studio": "A premium minimalist studio with soft, controlled commercial lighting.",
    "home": "A tasteful, modern, warm home interior with natural daylight.",
    "cafe": "A stylish modern cafe with warm ambient light and a softly blurred background.",
}
GOAL_LABELS = {
    "shopee": "Shopee Affiliate: clear, trustworthy product presentation that makes product details easy to see.",
    "tiktok": "TikTok Viral: a visually strong opening frame with lively composition while keeping the product unmistakably clear.",
}


def build_storyboard_prompt(goal, style, environment, attributes=None):
    """Build one vertical storyboard/key-visual prompt without making API calls."""
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
        "Use the uploaded reference photograph as the sole source of truth for product-specific details; "
        "do not guess unseen specifications."
    )
    return (
        "Create ONE photorealistic vertical 9:16 storyboard key visual for a product advertisement. "
        "This is one complete image, NOT a multi-panel storyboard, grid, collage, contact sheet, or video. "
        f"Campaign objective: {goal_text} "
        f"Visual direction: {style_text} "
        f"Background: {environment_text} "
        f"{observations} "
        "REFERENCE LOCK: Treat the uploaded product photograph as the authoritative visual reference. "
        "Preserve the exact product identity, silhouette, proportions, colour, material, texture, pattern, "
        "stitching, hardware, accessories, and any visible original logo. Do not redesign, replace, invent, "
        "or omit product features. If a detail is unclear, keep it faithful to the reference rather than guessing. "
        "Use realistic commercial photography, intentional composition, natural perspective, premium lighting, "
        "sharp product focus, and a clean background. No extra text, captions, subtitles, watermarks, fake logos, "
        "or decorative typography. Output exactly one image in a vertical 9:16 composition."
    )


def image_api_enabled():
    """Require explicit opt-in so an API request cannot unexpectedly incur charges."""
    return os.environ.get("KLIPPO_ENABLE_GEMINI_IMAGE_API", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _reference_jpeg(image_bytes):
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue()
    except Exception as exc:
        raise StoryboardEngineError("Gambar produk tidak dapat dibaca. Sila muat naik gambar lain.") from exc


def generate_storyboard_image(image_bytes, prompt, api_key=None, model=None):
    """Generate one 9:16 image only after explicit API-cost opt-in."""
    if not image_api_enabled():
        raise StoryboardEngineError(
            "Penjanaan imej API belum diaktifkan untuk mengelakkan caj tanpa kebenaran. "
            "Salin prompt ini ke aplikasi Gemini dan lampirkan gambar produk asal."
        )
    api_key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    model = (model or os.environ.get("GEMINI_STORYBOARD_IMAGE_MODEL", "")).strip()
    if not api_key:
        raise StoryboardEngineError("GEMINI_API_KEY belum ditetapkan pada servis beta.")
    if not model or not all(char.isalnum() or char in ".-_" for char in model):
        raise StoryboardEngineError("Tetapkan nama model Gemini Image yang sah selepas mengesahkan akses dan kos API.")
    reference = _reference_jpeg(image_bytes)
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(reference).decode("ascii"),
                }},
            ],
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "responseFormat": {"image": {"aspectRatio": "9:16", "imageSize": "1K"}},
        },
    }
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + model + ":generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise StoryboardEngineError("Kuota atau had Gemini Image telah dicapai. Semak kuota API projek.") from None
        if exc.code in (401, 403):
            raise StoryboardEngineError("Projek atau API key tidak mempunyai akses kepada model imej ini.") from None
        if exc.code == 404:
            raise StoryboardEngineError("Model imej tidak ditemui atau tidak tersedia untuk projek ini.") from None
        raise StoryboardEngineError(f"Gemini Image gagal (HTTP {exc.code}).") from None
    except Exception:
        raise StoryboardEngineError("Sambungan ke Gemini Image gagal atau tamat masa.") from None

    candidates = result.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    for part in parts:
        blob = part.get("inlineData") or part.get("inline_data") or {}
        data = blob.get("data")
        mime = blob.get("mimeType") or blob.get("mime_type") or ""
        if data and mime.startswith("image/"):
            try:
                raw = base64.b64decode(data)
                with Image.open(BytesIO(raw)) as image:
                    image.load()
                    output = BytesIO()
                    image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
                    return output.getvalue()
            except Exception as exc:
                raise StoryboardEngineError("Gemini memulangkan imej yang tidak sah.") from exc
    raise StoryboardEngineError("Gemini tidak memulangkan imej. Cuba prompt atau gambar lain.")
