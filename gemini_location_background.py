"""Generate reusable photorealistic location backgrounds with Gemini Image."""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image


class GeminiLocationBackgroundError(RuntimeError):
    """Safe user-facing location-background generation error."""


def generate_location_background(scene_description: str) -> bytes:
    """Return a clean vertical background plate; product is composited locally."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiLocationBackgroundError("GEMINI_API_KEY belum ditetapkan pada bot.")
    model = os.environ.get("GEMINI_PRODUCT_IMAGE_MODEL", "gemini-2.5-flash-image").strip()
    if not model or not all(char.isalnum() or char in ".-_" for char in model):
        raise GeminiLocationBackgroundError("Nama model imej Gemini tidak sah.")
    prompt = (
        "Generate ONE photorealistic vertical 9:16 commercial photography background plate. "
        "Scene: " + (scene_description or "a premium neutral indoor location") + ". "
        "The scene must be a believable real place with realistic materials, perspective, "
        "natural lighting and subtle depth of field. Leave a clean, uncluttered central foreground "
        "area for a product to be composited later, with plausible surface/contact area and no object "
        "covering that area. No product, no people, no hands, no logos, no watermarks, no captions, "
        "no readable text, no collage, no split screen, no illustration or CGI look. "
        "Make the background suitable for a realistic product advertisement."
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "responseMimeType": "image/png"},
    }
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise GeminiLocationBackgroundError(
                "Kuota atau had permintaan Gemini Image telah dicapai. Cuba lagi kemudian."
            ) from None
        if exc.code in (401, 403):
            raise GeminiLocationBackgroundError(
                "API key atau projek Google AI tiada akses kepada model imej Gemini. Semak akses dan pengebilan."
            ) from None
        if exc.code == 404:
            raise GeminiLocationBackgroundError(
                "Model imej Gemini tidak ditemui. Semak GEMINI_PRODUCT_IMAGE_MODEL."
            ) from None
        raise GeminiLocationBackgroundError(
            "Gemini Image gagal menjana latar tempat (HTTP %s)." % exc.code
        ) from None
    except Exception:
        raise GeminiLocationBackgroundError("Sambungan Gemini Image gagal atau tamat masa.") from None

    candidates = result.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    for part in parts:
        blob = part.get("inlineData") or part.get("inline_data") or {}
        raw = blob.get("data")
        mime = blob.get("mimeType") or blob.get("mime_type") or ""
        if raw and mime.startswith("image/"):
            try:
                with Image.open(BytesIO(base64.b64decode(raw))) as opened:
                    image = opened.convert("RGB")
                    out = BytesIO()
                    image.save(out, format="PNG", optimize=True)
                    return out.getvalue()
            except Exception as exc:
                raise GeminiLocationBackgroundError("Gemini memulangkan imej latar yang tidak sah.") from exc
    feedback = result.get("promptFeedback", {}).get("blockReason")
    if feedback:
        raise GeminiLocationBackgroundError("Gemini menyekat permintaan latar ini. Cuba pilihan lain.")
    raise GeminiLocationBackgroundError("Gemini tidak memulangkan imej latar. Cuba semula.")
