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
GEMINI_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-3.5-flash-lite").strip()


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


def analyze_product(image_path: Path) -> dict:
    """Return Gemini-verified visible attributes as JSON; conservative fallback if unavailable."""
    fallback = {
        "product_type": "tidak pasti", "colors": [], "shape": "rujuk bentuk yang kelihatan dalam gambar",
        "materials": [], "logo_or_text": "kekalkan hanya teks/logo yang jelas; jangan reka teks kabur",
        "visible_details": [], "uncertainties": ["analisis Gemini tidak tersedia"],
        "voiceover_ms": "Lihat produk ini dengan reka bentuk dan perincian yang menarik."
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
        "uncertainties (array), voiceover_ms (one short natural Malaysian Malay voiceover sentence). "
        "Only report directly visible facts. Never guess brand/model, exact material, product claims, benefits, "
        "or unreadable text. If uncertain, say 'tidak pasti'."
    )
    body = {"contents": [{"parts": [
        {"text": prompt},
        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")}}
    ]}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": 650, "responseMimeType": "application/json"}}
    started = time.perf_counter()
    # Gemini 2.5 Flash may return 404 for projects without prior access.
    # Try the configured model first, then one current, cost-efficient multimodal fallback.
    candidate_models = list(dict.fromkeys([GEMINI_MODEL, "gemini-3.5-flash-lite"]))
    try:
        result = None
        selected_model = GEMINI_MODEL
        for candidate_model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent"
            request = urllib.request.Request(url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    result = json.load(response)
                selected_model = candidate_model
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and candidate_model != candidate_models[-1]:
                    logging.warning("Gemini model %s returned HTTP 404; retrying once with %s",
                                    candidate_model, candidate_models[-1])
                    continue
                raise
        if result is None:
            raise RuntimeError("Gemini returned no result from configured or fallback model.")
        logging.info("Gemini model selected: %s; analysis latency: %.2fs",
                     selected_model, time.perf_counter() - started)
        text = "".join(part.get("text", "") for part in
            result.get("candidates", [{}])[0].get("content", {}).get("parts", [])).strip()
        attributes = parse_gemini_json(text)
        for name, default in fallback.items():
            attributes.setdefault(name, default)
        usage = result.get("usageMetadata", {})
        if usage:
            logging.info("Gemini usage: prompt=%s output=%s total=%s tokens",
                usage.get("promptTokenCount", "n/a"), usage.get("candidatesTokenCount", "n/a"),
                usage.get("totalTokenCount", "n/a"))
        return attributes
    except Exception as exc:
        detail = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        raise RuntimeError(f"Gemini JSON analysis failed ({detail}); fal.ai generation was not started.") from exc


def generate_panel(image_url: str, attributes: dict, scene: str, index: int) -> tuple[bytes, float]:
    verified = json.dumps({k: attributes.get(k) for k in
        ("product_type", "colors", "shape", "materials", "logo_or_text", "visible_details", "uncertainties")},
        ensure_ascii=False)
    prompt = (
        "Create ONE photorealistic vertical 9:16 product-ad storyboard frame from the supplied reference image. "
        "The reference is the sole source of truth. Preserve the exact product identity, silhouette, proportions, "
        "colors, material appearance, printed label, logo, pattern, and visible accessories. Do not redesign or "
        "invent product details. No added text, captions, watermarks, or extra logos. One scene only, no collage. "
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
        narration = str(attributes.get("voiceover_ms") or "Lihat produk ini dengan reka bentuk dan perincian yang menarik.")
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
