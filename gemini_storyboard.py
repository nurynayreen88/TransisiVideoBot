"""Gemini API storyboard generation with model fallback for HTTP 404."""
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
    configured_model = os.environ.get("GEMINI_STORYBOARD_MODEL", "").strip()
    model = configured_model or "gemini-3.8-flash"
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
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": 4096},
    }

    # If a configured/legacy model returns 404, try current stable alternatives.
    # Do not retry quota/auth failures because changing models will not fix them.
    candidates = [model]
    for fallback in ("gemini-3.8-flash", "gemini-3.5-flash-lite"):
        if fallback not in candidates:
            candidates.append(fallback)

    result = None
    last_model = model
    for candidate_model in candidates:
        request = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + candidate_model + ":generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=75) as response:
                result = json.load(response)
            last_model = candidate_model
            if candidate_model != model:
                logging.info("Gemini storyboard succeeded with fallback model %s", candidate_model)
            break
        except urllib.error.HTTPError as exc:
            last_model = candidate_model
            if exc.code == 404:
                logging.warning("Gemini storyboard model %s returned HTTP 404; trying fallback if available", candidate_model)
                continue
            if exc.code in (401, 403):
                raise GeminiStoryboardError(
                    "Kunci API Gemini tidak sah atau projek ini tiada akses kepada model. Semak API key dan akses Gemini API."
                ) from None
            if exc.code == 429:
                raise GeminiStoryboardError(
                    "Kuota atau had permintaan Gemini telah dicapai. Cuba lagi kemudian."
                ) from None
            logging.warning("Gemini storyboard API returned HTTP %s", exc.code)
            raise GeminiStoryboardError(
                "Gemini API gagal memproses permintaan (HTTP %s)." % exc.code
            ) from None
        except Exception as exc:
            logging.warning("Gemini storyboard API unavailable (%s)", type(exc).__name__)
            raise GeminiStoryboardError("Sambungan ke Gemini gagal atau tamat masa.") from None

    if result is None:
        logging.error("Gemini storyboard: all candidate models returned HTTP 404; last model=%s", last_model)
        raise GeminiStoryboardError(
            "Model Gemini tidak ditemui (HTTP 404). Tetapkan GEMINI_STORYBOARD_MODEL kepada model yang tersedia untuk API key ini, kemudian cuba semula."
        )

    responses = result.get("candidates") or []
    response_parts = responses[0].get("content", {}).get("parts", []) if responses else []
    output = "\\n".join(part.get("text", "") for part in response_parts).strip()
    if not output:
        feedback = result.get("promptFeedback", {}).get("blockReason")
        if feedback:
            raise GeminiStoryboardError("Gemini menyekat permintaan ini. Cuba ubah arahan atau gambar.")
        raise GeminiStoryboardError("Gemini tidak menghasilkan teks storyboard.")
    return output[:24000]


async def generate_storyboard(images: list[bytes], instructions: str) -> str:
    """Run the blocking Gemini request off the Telegram event loop."""
    return await asyncio.to_thread(_generate, images, instructions)
