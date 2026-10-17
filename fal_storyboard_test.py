"""Two-panel fal.ai storyboard test with Gemini JSON analysis and timing metrics.

Usage:
  python fal_storyboard_test.py product.jpg --out fal_storyboard_test_output

Requires FAL_KEY and GEMINI_API_KEY. No credentials are stored in this file.
"""
import argparse
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import fal_client
import requests
from PIL import Image, ImageDraw

MODEL = os.environ.get("FAL_STORYBOARD_MODEL", "fal-ai/flux-kontext/dev").strip()
GEMINI_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash").strip()


def analyze_product(image_path: Path) -> dict:
    """Return Gemini-verified visible attributes as JSON; conservative fallback if unavailable."""
    import base64
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    fallback = {
        "product_type": "not certain",
        "colors": [],
        "shape": "only use the visible shape in the reference",
        "materials": [],
        "logo_or_text": "preserve only clearly legible visible text/logo; do not recreate uncertain text",
        "visible_details": [],
        "uncertainties": ["Gemini analysis unavailable; reference image is the source of truth"],
        "voiceover_ms": "Lihat produk ini dengan reka bentuk dan perincian yang menarik.",
    }
    if not key:
        logging.warning("GEMINI_API_KEY missing; using conservative visual fallback.")
        return fallback
    data = image_path.read_bytes()
    if len(data) > 8_000_000:
        logging.warning("Image exceeds Gemini inline limit; using conservative fallback.")
        return fallback
    prompt = (
        "Analyse this product photo. Return ONLY valid JSON with keys: "
        "product_type (string), colors (array of strings), shape (string), materials (array of strings), "
        "logo_or_text (string), visible_details (array of strings), uncertainties (array of strings), "
        "voiceover_ms (one short natural Malaysian Malay voiceover sentence, no invented claims). "
        "Only report directly visible facts. Never guess brand/model, exact material, product claims, capacity, "
        "benefits, or unreadable text. If uncertain, say 'tidak pasti'. Preserve the exact visible product identity."
    )
    body = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(data).decode("ascii")}}
        ]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 650,
            "responseMimeType": "application/json"
        }
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)
        logging.info("Gemini analysis latency: %.2fs", time.perf_counter() - started)
        text = "".join(part.get("text", "") for part in
            result.get("candidates", [{}])[0].get("content", {}).get("parts", [])).strip()
        attrs = json.loads(text)
        for name, default in fallback.items():
            attrs.setdefault(name, default)
        usage = result.get("usageMetadata", {})
        if usage:
            logging.info("Gemini usage metadata: prompt_tokens=%s output_tokens=%s total_tokens=%s",
                usage.get("promptTokenCount", "n/a"), usage.get("candidatesTokenCount", "n/a"),
                usage.get("totalTokenCount", "n/a"))
        return attrs
    except Exception as exc:
        logging.warning("Gemini JSON analysis failed (%s); using conservative fallback.", type(exc).__name__)
        return fallback


def generate_panel(image_url: str, attributes: dict, scene: str, index: int) -> tuple[bytes, float]:
    verified = json.dumps({k: attributes.get(k) for k in
        ("product_type", "colors", "shape", "materials", "logo_or_text", "visible_details", "uncertainties")},
        ensure_ascii=False)
    prompt = (
        "Create ONE photorealistic vertical 9:16 product-ad storyboard frame from the supplied reference image. "
        "The source photograph is the sole source of truth. Preserve the exact product identity, silhouette, "
        "proportions, colors, material appearance, printed label, logo, pattern, and visible accessories as closely "
        "as possible. Do not redesign, replace, or invent product details. No added text, captions, watermarks, "
        "or extra logos. One scene only, no collage or multi-panel grid. Natural realistic commercial lighting. "
        f"Gemini JSON observations (uncertainties must not be guessed): {verified[:1800]} "
        f"Storyboard panel {index}: {scene}"
    )
    started = time.perf_counter()
    result = fal_client.subscribe(
        MODEL,
        arguments={"image_url": image_url, "prompt": prompt, "num_inference_steps": 28,
                   "num_images": 1, "output_format": "jpeg", "aspect_ratio": "9:16"},
        with_logs=False,
        client_timeout=240,
    )
    images = result.get("images") or []
    if not images or not images[0].get("url"):
        raise RuntimeError("fal.ai returned no image URL; response keys: " + ", ".join(result.keys()))
    response = requests.get(images[0]["url"], timeout=60)
    response.raise_for_status()
    elapsed = time.perf_counter() - started
    return response.content, elapsed


def make_contact_sheet(panel_paths: list[Path], output_path: Path) -> None:
    cells = []
    for path in panel_paths:
        with Image.open(path) as im:
            cells.append(im.convert("RGB").resize((540, 720), Image.Resampling.LANCZOS))
    canvas = Image.new("RGB", (1100, 790), "#f4f0e9")
    draw = ImageDraw.Draw(canvas)
    for i, cell in enumerate(cells):
        x = 10 + i * 550
        canvas.paste(cell, (x, 45))
        draw.text((x + 12, 14), f"PANEL {i + 1}", fill="#242424")
    canvas.save(output_path, quality=92)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate exactly two fal.ai storyboard panels and report latency.")
    parser.add_argument("image", help="Path to one product reference image")
    parser.add_argument("--out", default="fal_storyboard_test_output", help="Output folder")
    args = parser.parse_args()
    if not os.environ.get("FAL_KEY", "").strip():
        parser.error("FAL_KEY is missing. Set it as an environment variable; never hardcode it.")
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        parser.error(f"Image file not found: {image_path}")
    output_dir = Path(args.out).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    total_started = time.perf_counter()
    attributes = analyze_product(image_path)
    (output_dir / "product_attributes.json").write_text(
        json.dumps(attributes, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Gemini JSON attributes saved:", output_dir / "product_attributes.json")
    print("Uploading reference image to fal.ai...")
    upload_started = time.perf_counter()
    image_url = fal_client.upload_file(str(image_path))
    print(f"fal.ai upload latency: {time.perf_counter() - upload_started:.2f}s")

    scenes = [
        "Opening hero shot: product clearly visible in a tasteful clean setting, three-quarter view.",
        "Detail shot: closer framing on the same product, showing only visible real details and gentle highlights."
    ]
    generated = []
    for index, scene in enumerate(scenes, start=1):
        print(f"Generating panel {index}/2 with {MODEL}...")
        data, elapsed = generate_panel(image_url, attributes, scene, index)
        path = output_dir / f"panel_{index}.jpg"
        with Image.open(__import__("io").BytesIO(data)) as im:
            im.convert("RGB").save(path, "JPEG", quality=94, optimize=True)
        generated.append(path)
        print(f"Panel {index} latency (generation + download): {elapsed:.2f}s; saved: {path}")
    sheet = output_dir / "contact_sheet_2_panels.jpg"
    make_contact_sheet(generated, sheet)
    print(f"Contact sheet: {sheet}")
    print(f"Total latency: {time.perf_counter() - total_started:.2f}s")
    print("Cost: check the fal.ai Usage/Billing dashboard before and after this run; this script does not guess a price.")
    print("Quality check: compare the original against both panels, especially logo/text, silhouette, colour and materials.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
