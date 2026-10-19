"""Two-panel fal.ai storyboard test with Gemini JSON analysis and timing metrics."""
import argparse
import base64
import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path

import fal_client
import requests
from PIL import Image, ImageDraw
from modules.video_engine import create_video

MODEL = os.environ.get("FAL_STORYBOARD_MODEL", "fal-ai/flux-kontext/dev").strip()
GEMINI_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash").strip()


def detect_image_mime(image_path: str | Path) -> str:
    """Detect and validate the actual image format instead of assuming JPEG."""
    mime_by_format = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    try:
        with Image.open(image_path) as image:
            image_format = (image.format or "").upper()
            image.verify()
    except Exception as exc:
        raise ValueError("Reference file is not a valid supported image.") from exc
    if image_format not in mime_by_format:
        raise ValueError(f"Unsupported image format: {image_format or 'unknown'}. Use JPEG, PNG, or WEBP.")
    return mime_by_format[image_format]


def parse_gemini_json(text: str) -> dict:
    """Parse a JSON object, tolerating a surrounding Markdown code fence."""
    cleaned = text.strip()
    match = re.fullmatch(r"^\x60{3}(?:json)?\s*(.*?)\s*\x60{3}$", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("Gemini response must be a JSON object.")
    return value


def normalize_malaysian_voiceover(text: str, visible_details=None, product_type=None) -> str:
    """Localize common Indonesian forms and produce a detail-led Malaysian fallback if needed."""
    value = str(text or "").strip()
    replacements = (
        (r"\bbagus banget\b", "sangat bagus"),
        (r"\bbagus sekali\b", "sangat bagus"),
        (r"\bbanget\b", "sangat"),
        (r"\bnggak\b|\benggak\b", "tak"),
        (r"\bkalian\b", "anda"),
        (r"\bbisa\b", "boleh"),
        (r"\bsilakan\b", "sila"),
        (r"\bcoba\b", "cuba"),
        (r"\bkualitas\b", "kualiti"),
        (r"\bdesain\b", "reka bentuk"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)

    if not value:
        detail = ""
        if isinstance(visible_details, (list, tuple)) and visible_details:
            candidate = str(visible_details[0] or "").strip().strip(". ")
            if candidate and not re.search(r"\b(?:unknown|uncertain|not sure|tidak pasti)\b", candidate, re.I):
                detail = candidate
        type_map = {
            "ring": "cincin", "jewellery": "aksesori", "jewelry": "aksesori",
            "bag": "beg", "handbag": "beg tangan", "backpack": "beg galas",
            "watch": "jam tangan", "phone": "telefon", "smartphone": "telefon pintar",
            "shoe": "kasut", "shoes": "kasut", "bottle": "botol",
            "beauty product": "produk kecantikan", "cosmetic": "produk kosmetik",
            "stationery": "alat tulis", "appliance": "peralatan elektrik",
        }
        type_key = str(product_type or "").strip().lower()
        type_ms = type_map.get(type_key, "")
        if detail and type_ms:
            value = f"Tengok {detail} pada {type_ms} ini—jom lihat dengan lebih dekat."
        elif detail:
            value = f"Tengok {detail} ini—jom lihat dengan lebih dekat."
        elif type_ms:
            value = f"Tengok {type_ms} ini—jom semak butirannya."
        else:
            value = "Tengok butiran yang jelas pada produk ini—jom lihat dengan lebih dekat."

    value = re.sub(r"\s+", " ", value).strip(" \t\r\n\"'")
    first_sentence = re.split(r"(?<=[.!?])\s+", value, maxsplit=1)[0].strip()
    words = first_sentence.split()
    if len(words) > 18:
        first_sentence = " ".join(words[:18]).rstrip(" ,;:") + "."
    return first_sentence or "Tengok butiran produk ini—jom lihat dengan lebih dekat."

def analyze_product(image_path: Path) -> dict:
    """Return Gemini-verified visible attributes as JSON; conservative fallback if unavailable."""
    fallback = {
        "product_type": "tidak pasti", "colors": [], "shape": "rujuk bentuk yang kelihatan dalam gambar",
        "materials": [], "logo_or_text": "kekalkan hanya teks/logo yang jelas; jangan reka teks kabur",
        "visible_details": [], "uncertainties": ["analisis Gemini tidak tersedia"],
        "voiceover_ms": ""
    }
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required: Gemini JSON analysis must run before fal.ai.")
    mime_type = detect_image_mime(image_path)
    data = image_path.read_bytes()
    if len(data) > 8_000_000:
        raise RuntimeError("Image exceeds Gemini inline limit (8 MB). Resize the reference image and retry.")
    prompt = (
        "Analyse this product photo. Return ONLY valid JSON with keys: product_type (string), "
        "colors (array), shape (string), materials (array), logo_or_text (string), visible_details (array), "
        "uncertainties (array), voiceover_ms (one short spoken line in natural Bahasa Melayu Malaysia). "
        "The voiceover MUST sound like a native Malaysian product promoter with Malaysian vocabulary, pronunciation, "
        "rhythm and intonation. Indonesian accent and Indonesian vocabulary are prohibited; avoid 'banget', 'nggak', "
        "'kalian', 'bisa' and 'silakan'. Use varied, natural openings instead of repeating 'Kenali produk ini' or "
        "the same generic phrase. When supported by the visible details, structure the line as a short spoken hook, "
        "one concrete visible detail, and a soft CTA. Keep it under 18 words, easy to pronounce, and never invent "
        "price, discounts, stock, guarantees, performance claims, benefits, materials or unreadable text. "
        "Write visible_details in natural Bahasa Melayu Malaysia so a safe detail-led fallback can use them. "
        "Only report directly visible facts; if uncertain, say 'tidak pasti'."
    )
    body = {"contents": [{"parts": [
        {"text": prompt},
        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")}}
    ]}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": 650, "responseMimeType": "application/json"}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    request = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        logging.info("Gemini analysis latency: %.2fs", time.perf_counter() - started)
        text = "".join(part.get("text", "") for part in
            result.get("candidates", [{}])[0].get("content", {}).get("parts", [])).strip()
        attributes = parse_gemini_json(text)
        for name, default in fallback.items():
            attributes.setdefault(name, default)
        attributes["voiceover_ms"] = normalize_malaysian_voiceover(attributes.get("voiceover_ms", ""), attributes.get("visible_details"), attributes.get("product_type"))
        usage = result.get("usageMetadata", {})
        if usage:
            logging.info("Gemini usage: prompt=%s output=%s total=%s tokens",
                usage.get("promptTokenCount", "n/a"), usage.get("candidatesTokenCount", "n/a"),
                usage.get("totalTokenCount", "n/a"))
        return attributes
    except Exception as exc:
        raise RuntimeError(f"Gemini JSON analysis failed ({type(exc).__name__}); fal.ai generation was not started.") from exc


def generate_panel(image_url: str, attributes: dict, scene: str, index: int) -> tuple[bytes, float]:
    verified = json.dumps({k: attributes.get(k) for k in
        ("product_type", "colors", "shape", "materials", "logo_or_text", "visible_details", "uncertainties")},
        ensure_ascii=False)
    prompt = (
        "Create ONE photorealistic vertical 9:16 product-ad storyboard frame from the supplied reference image. "
        "The reference is the sole source of truth. Preserve the exact product identity, silhouette, proportions, "
        "colors, material appearance, printed label, logo, pattern, and visible accessories. Do not redesign or "
        "invent product details. No added text, captions, watermarks, or extra logos. One scene only, no collage. "
        "REALISTIC PHYSICAL SCALE IS MANDATORY: keep the product's true category-appropriate size relative to hands, "
        "fingers, people, furniture, and the environment. A ring must fit naturally on a finger and must never be "
        "as large as a table. Use macro camera framing rather than enlarging a small object. Watches must fit wrists, "
        "phones must fit hands, and scale must stay consistent in every panel. No giant products, warped geometry, "
        "floating objects, or impossible interactions. If exact dimensions are unknown, use ordinary realistic proportions. "
        f"Gemini JSON observations; do not guess uncertain details: {verified[:1800]} "
        f"Storyboard panel {index}: {scene}"
    )
    started = time.perf_counter()
    result = fal_client.subscribe(
        MODEL,
        arguments={"image_url": image_url, "prompt": prompt, "num_inference_steps": 28,
                   "num_images": 1, "output_format": "jpeg", "aspect_ratio": "9:16"},
        with_logs=False, client_timeout=240,
    )
    images = result.get("images") or []
    if not images or not images[0].get("url"):
        raise RuntimeError("fal.ai returned no image URL; response keys: " + ", ".join(result.keys()))
    response = requests.get(images[0]["url"], timeout=60)
    response.raise_for_status()
    return response.content, time.perf_counter() - started


def make_contact_sheet(panel_paths: list[Path], output_path: Path) -> None:
    canvas = Image.new("RGB", (1100, 790), "#f4f0e9")
    draw = ImageDraw.Draw(canvas)
    for i, path in enumerate(panel_paths):
        with Image.open(path) as image:
            cell = image.convert("RGB").resize((540, 720), Image.Resampling.LANCZOS)
        x = 10 + i * 550
        canvas.paste(cell, (x, 45))
        draw.text((x + 12, 14), f"PANEL {i + 1}", fill="#242424")
    canvas.save(output_path, quality=92)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate exactly two fal.ai storyboard panels and report latency.")
    parser.add_argument("image", help="Path to product reference image")
    parser.add_argument("--out", default="fal_storyboard_test_output", help="Output folder")
    parser.add_argument("--no-video", action="store_true", help="Generate only panels and contact sheet")
    args = parser.parse_args()
    if not os.environ.get("FAL_KEY", "").strip():
        parser.error("FAL_KEY is missing. Set it as an environment variable; never hardcode it.")
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        parser.error(f"Image file not found: {image_path}")
    output_dir = Path(args.out).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    attributes = analyze_product(image_path)
    (output_dir / "product_attributes.json").write_text(
        json.dumps(attributes, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Gemini JSON attributes saved:", output_dir / "product_attributes.json")
    upload_started = time.perf_counter()
    image_url = fal_client.upload_file(str(image_path))
    print(f"fal.ai upload latency: {time.perf_counter() - upload_started:.2f}s")
    scenes = [
        "Opening hero shot: product clearly visible in a tasteful clean setting, three-quarter view.",
        "Detail shot: closer framing on the same product, showing only real visible details and gentle highlights."
    ]
    generated = []
    for index, scene in enumerate(scenes, start=1):
        print(f"Generating panel {index}/2 with {MODEL}...")
        data, elapsed = generate_panel(image_url, attributes, scene, index)
        path = output_dir / f"panel_{index}.jpg"
        with Image.open(__import__("io").BytesIO(data)) as image:
            image.convert("RGB").save(path, "JPEG", quality=94, optimize=True)
        generated.append(path)
        print(f"Panel {index} latency including download: {elapsed:.2f}s; saved: {path}")
    sheet = output_dir / "contact_sheet_2_panels.jpg"
    make_contact_sheet(generated, sheet)
    print("Contact sheet:", sheet)
    if not args.no_video:
        video_path = output_dir / "video_output.mp4"
        narration = normalize_malaysian_voiceover(attributes.get("voiceover_ms", ""), attributes.get("visible_details"), attributes.get("product_type"))
        print("Creating vertical video with complete Malay voiceover...")
        create_video(generated, narration, video_path)
        print("Video:", video_path)
    print(f"Total latency: {time.perf_counter() - started:.2f}s")
    print("Check fal.ai Usage/Billing before and after this run for actual credit/cost; script does not guess pricing.")
    print("Compare original vs panels: silhouette, colours, material appearance, logo/text and accessories.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
