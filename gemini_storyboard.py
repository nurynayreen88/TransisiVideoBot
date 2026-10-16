"""Gemini API storyboard generation using the free-tier REST endpoint."""
import asyncio
import base64
import json
import logging
import os
import urllib.error
import urllib.request


class GeminiStoryboardError(RuntimeError):
    """Safe, user-facing storyboard generation error."""


def _generate(images: list[bytes], instructions: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiStoryboardError("GEMINI_API_KEY belum ditetapkan dalam environment bot.")
    model = os.environ.get("GEMINI_STORYBOARD_MODEL", "gemini-2.5-flash").strip()
    if not model or not all(char.isalnum() or char in ".-_" for char in model):
        raise GeminiStoryboardError("Nama model Gemini tidak sah.")
    if not images:
        raise GeminiStoryboardError("Sekurang-kurangnya satu gambar rujukan diperlukan.")
    parts = [{"text": instructions}]
    for data in images[:4]:
        if not data or len(data) > 8_000_000:
            continue
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(data).decode("ascii"),
            }
        })
    if len(parts) == 1:
        raise GeminiStoryboardError("Gambar rujukan kosong atau terlalu besar.")
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.65,
            "maxOutputTokens": 4096,
        },
    }
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + model + ":generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=75) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise GeminiStoryboardError("Kunci API Gemini tidak sah atau akses model tidak tersedia.") from None
        if exc.code == 429:
            raise GeminiStoryboardError("Kuota atau had permintaan Gemini telah dicapai. Cuba lagi kemudian.") from None
        logging.warning("Gemini storyboard API returned HTTP %s", exc.code)
        raise GeminiStoryboardError("Gemini API tidak dapat memproses permintaan (HTTP %s)." % exc.code) from None
    except Exception as exc:
        logging.warning("Gemini storyboard API unavailable (%s)", type(exc).__name__)
        raise GeminiStoryboardError("Sambungan ke Gemini gagal atau tamat masa.") from None
    candidates = result.get("candidates") or []
    response_parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    text = "\n".join(part.get("text", "") for part in response_parts).strip()
    if not text:
        feedback = result.get("promptFeedback", {}).get("blockReason")
        if feedback:
            raise GeminiStoryboardError("Gemini menyekat permintaan ini. Cuba ubah arahan atau gambar.")
        raise GeminiStoryboardError("Gemini tidak menghasilkan teks storyboard.")
    return text[:24000]


async def generate_storyboard(images: list[bytes], instructions: str) -> str:
    """Run the blocking Gemini request off the Telegram event loop."""
    return await asyncio.to_thread(_generate, images, instructions)
