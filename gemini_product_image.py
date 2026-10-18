"""Opt-in Gemini API generation of a product-preserving reference image."""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image, ImageOps


class GeminiProductImageError(RuntimeError):
    """Safe, user-facing product image generation error."""


def _prepare_image(data: bytes) -> tuple[str, str]:
    try:
        with Image.open(BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
            out = BytesIO()
            image.save(out, format="JPEG", quality=88, optimize=True)
            return base64.b64encode(out.getvalue()).decode("ascii"), "image/jpeg"
    except Exception as exc:
        raise GeminiProductImageError("Gambar produk tidak dapat diproses.") from exc


def generate_product_reference_image(image_bytes: bytes, image_prompt: str) -> bytes:
    """Edit one uploaded product reference into a premium 9:16 scene using Gemini."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiProductImageError("GEMINI_API_KEY belum ditetapkan pada bot.")
    if not image_bytes:
        raise GeminiProductImageError("Sila muat naik gambar produk terlebih dahulu.")
    model = os.environ.get("GEMINI_PRODUCT_IMAGE_MODEL", "gemini-2.5-flash-image").strip()
    if not model or not all(char.isalnum() or char in ".-_" for char in model):
        raise GeminiProductImageError("Nama model imej Gemini tidak sah.")

    encoded, mime_type = _prepare_image(image_bytes)
    prompt = (
        "Edit the attached product reference into ONE premium, photorealistic commercial product image. "
        "Use the uploaded photo as the source of truth for the product, not as loose inspiration. "
        "Preserve the exact visible product identity, shape, proportions, colour, print, pattern, packaging, "
        "hardware, visible logo and component count. Do not redesign, recolour, replace, duplicate, remove, "
        "or invent product details. Change only the scene, lighting, composition and human presentation "
        "requested by the prompt. Keep any original printed product logo only where it already appears; "
        "never add separate logos, watermarks, captions, readable text, interface elements or end cards. "
        "Create a single cohesive vertical 9:16 photograph, realistic materials, natural contact shadows, "
        "physically plausible reflections, clean sharp product detail, no collage or split screen. "
        "If exact product fidelity conflicts with a creative request, prioritize product fidelity.\n\n"
        "USER'S IMAGE PROMPT:\n" + (image_prompt or "")[:8000]
    )
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": encoded}},
            ],
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "response_mime_type": "image/png",
        },
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
            raise GeminiProductImageError(
                "Kuota atau had permintaan Gemini Image telah dicapai. Cuba lagi kemudian."
            ) from None
        if exc.code in (401, 403):
            raise GeminiProductImageError(
                "API key atau projek Google AI tidak mempunyai akses kepada model imej Gemini. Semak akses dan pengebilan."
            ) from None
        if exc.code == 404:
            raise GeminiProductImageError(
                "Model imej Gemini tidak ditemui. Semak GEMINI_PRODUCT_IMAGE_MODEL dan akses API."
            ) from None
        raise GeminiProductImageError("Gemini Image gagal memproses permintaan (HTTP %s)." % exc.code) from None
    except Exception:
        raise GeminiProductImageError("Sambungan ke Gemini Image gagal atau tamat masa.") from None

    candidates = result.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    for part in parts:
        blob = part.get("inlineData") or part.get("inline_data") or {}
        raw = blob.get("data")
        mime = blob.get("mimeType") or blob.get("mime_type") or ""
        if raw and mime.startswith("image/"):
            try:
                output = BytesIO(base64.b64decode(raw))
                with Image.open(output) as opened:
                    image = opened.convert("RGB")
                    result_bytes = BytesIO()
                    image.save(result_bytes, format="PNG", optimize=True)
                    return result_bytes.getvalue()
            except Exception as exc:
                raise GeminiProductImageError("Gemini memulangkan imej yang tidak sah.") from exc
    feedback = result.get("promptFeedback", {}).get("blockReason")
    if feedback:
        raise GeminiProductImageError("Gemini menyekat permintaan imej ini. Cuba gambar atau arahan lain.")
    raise GeminiProductImageError("Gemini tidak memulangkan imej. Cuba semula.")
