"""Generate a visual storyboard contact sheet with Gemini image generation."""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image, ImageOps


class GeminiStoryboardImageError(RuntimeError):
    """Safe, user-facing storyboard image generation error."""


def _jpeg_bytes(data: bytes) -> bytes:
    try:
        with Image.open(BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            out = BytesIO()
            image.save(out, format="JPEG", quality=88, optimize=True)
            return out.getvalue()
    except Exception as exc:
        raise GeminiStoryboardImageError("Gambar rujukan tidak dapat diproses.") from exc


def generate_storyboard_sheet(images: list[bytes], storyboard_text: str,
                              duration: int, sheet_number: int = 1,
                              language: str = "Bahasa Melayu") -> bytes:
    """Return one illustrated storyboard sheet (2x2 panels) as PNG bytes."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiStoryboardImageError("GEMINI_API_KEY belum ditetapkan.")
    if not images:
        raise GeminiStoryboardImageError("Gambar rujukan diperlukan untuk storyboard bergambar.")

    total_scenes = 4 if duration <= 10 else (6 if duration <= 15 else 8)
    start_scene = (sheet_number - 1) * 4 + 1
    end_scene = min(start_scene + 3, total_scenes)
    panel_count = end_scene - start_scene + 1
    prompt = (
        "Create ONE polished, illustrated product-ad storyboard contact sheet for a real short video. "
        "This must be an actual image, not text, not a collage of unrelated product photos, and not a poster. "
        "Use a strict 2-column by 2-row storyboard grid with clean equal-sized panels, thin dark gutters, "
        "clear panel boundaries, cinematic realistic photography, and consistent visual continuity. "
        "Preserve the exact product identity, color, shape, material, visible pattern, and accessories from "
        "the attached reference photos. Do not invent product details, extra logos, watermarks, subtitles, "
        "or decorative text. Each panel must depict a distinct consecutive moment from the supplied scene plan. "
        "Show camera framing, action, and emotion visually; use no written captions inside the panels. "
        "If fewer than four panels are requested, keep the unused grid cell(s) clean and blank rather than "
        "inventing extra scenes. Output a landscape 4:3 sheet.\n\n"
        f"VIDEO: exactly {duration} seconds, vertical-video concept 9:16, language for planning: {language}.\n"
        f"THIS IS SHEET {sheet_number}. Illustrate scenes {start_scene} through {end_scene} only "
        f"({panel_count} occupied panels).\n"
        "SCENE PLAN (use only the requested scene numbers, preserving sequence and continuity):\n"
        + storyboard_text[:18000]
    )

    parts = [{"text": prompt}]
    for data in images[:4]:
        if not data:
            continue
        compressed = _jpeg_bytes(data)
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(compressed).decode("ascii"),
            }
        })

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "responseFormat": {"image": {"aspectRatio": "4:3", "imageSize": "1K"}},
        },
    }
    model = os.environ.get("GEMINI_STORYBOARD_IMAGE_MODEL", "gemini-3.1-flash-image").strip()
    if not model or not all(c.isalnum() or c in ".-_" for c in model):
        raise GeminiStoryboardImageError("Nama model imej Gemini tidak sah.")
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
            raise GeminiStoryboardImageError(
                "Kuota atau had permintaan Gemini Image telah dicapai. Penjanaan storyboard bergambar menggunakan kuota berasingan."
            ) from None
        if exc.code in (401, 403):
            raise GeminiStoryboardImageError(
                "API key atau projek Google AI tidak mempunyai akses kepada model imej Gemini. Semak akses dan pengebilan API."
            ) from None
        if exc.code == 404:
            raise GeminiStoryboardImageError(
                "Model imej Gemini tidak ditemui. Semak akses model GEMINI_STORYBOARD_IMAGE_MODEL."
            ) from None
        raise GeminiStoryboardImageError("Gemini Image gagal memproses permintaan (HTTP %s)." % exc.code) from None
    except Exception as exc:
        raise GeminiStoryboardImageError("Sambungan ke Gemini Image gagal atau tamat masa.") from None

    candidates = result.get("candidates") or []
    response_parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    for part in response_parts:
        blob = part.get("inlineData") or part.get("inline_data") or {}
        data = blob.get("data")
        mime = blob.get("mimeType") or blob.get("mime_type") or ""
        if data and mime.startswith("image/"):
            try:
                raw = base64.b64decode(data)
                with Image.open(BytesIO(raw)) as opened:
                    output = BytesIO()
                    opened.convert("RGB").save(output, format="PNG", optimize=True)
                    return output.getvalue()
            except Exception as exc:
                raise GeminiStoryboardImageError("Gemini memulangkan imej yang tidak sah.") from exc
    feedback = result.get("promptFeedback", {}).get("blockReason")
    if feedback:
        raise GeminiStoryboardImageError("Gemini menyekat permintaan storyboard bergambar. Cuba gambar atau arahan lain.")
    raise GeminiStoryboardImageError("Gemini tidak memulangkan imej storyboard.");
