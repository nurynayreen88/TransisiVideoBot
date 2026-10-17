"""Internal-only fal.ai product storyboard experiment.

Usage:
  python fal_storyboard_test.py product.jpg

Requires FAL_KEY. If GEMINI_API_KEY is present, Gemini describes the product first.
This script is deliberately not imported by bot.py and does not change Telegram flows.
"""
import argparse
import asyncio
import logging
import os
from pathlib import Path

import fal_client
import requests
from PIL import Image, ImageDraw, ImageFont

MODEL = "fal-ai/flux-kontext/dev"


def product_description(image_path: Path) -> str:
    if os.environ.get("GEMINI_API_KEY", "").strip():
        try:
            from gemini_vision import describe_photo
            result = asyncio.run(describe_photo(image_path.read_bytes()))
            if result:
                return result
        except Exception as exc:
            logging.warning("Gemini product description unavailable (%s); use conservative fallback.", type(exc).__name__)
    return "Use only directly visible product details from the reference image. Preserve the exact product identity; do not invent brand, label text, colors, materials, or accessories."


def generate_panel(image_url: str, description: str, scene: str, index: int) -> bytes:
    prompt = (
        "Create one photorealistic frame for a product advertisement storyboard. "
        "Treat the attached image as the exact product reference. Preserve its identity, silhouette, "
        "colors, material, printed label, logo, proportions, and accessories as closely as possible. "
        "Do not redesign or replace the product. Do not add text, captions, watermarks, or extra logos. "
        "Show one coherent scene only; no collage or multi-panel grid. Vertical 9:16 composition. "
        "Use natural realistic lighting and a commercially polished but believable setting. "
        f"Verified product observations: {description[:1800]} "
        f"Storyboard frame {index}: {scene}"
    )
    result = fal_client.subscribe(
        MODEL,
        arguments={"image_url": image_url, "prompt": prompt, "num_inference_steps": 28},
        with_logs=False,
        client_timeout=180,
    )
    images = result.get("images") or []
    if not images or not images[0].get("url"):
        raise RuntimeError("fal.ai returned no image URL; response keys: " + ", ".join(result.keys()))
    response = requests.get(images[0]["url"], timeout=60)
    response.raise_for_status()
    return response.content


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
    parser = argparse.ArgumentParser(description="Generate a two-panel fal.ai storyboard test.")
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
    description = product_description(image_path)
    print("Gemini/visual description ready. Uploading reference image to fal.ai...")
    image_url = fal_client.upload_file(str(image_path))
    scenes = [
        "Hero opening shot: the product is clearly visible in a clean premium setting, three-quarter view, gentle camera perspective, product remains the main subject.",
        "Detail shot: closer framing on the same product and its real visible details, subtle natural highlights, same product design and color, no new accessories.",
    ]
    generated = []
    for index, scene in enumerate(scenes, start=1):
        print(f"Generating panel {index}/2 via {MODEL}...")
        data = generate_panel(image_url, description, scene, index)
        path = output_dir / f"panel_{index}.png"
        with Image.open(__import__("io").BytesIO(data)) as im:
            im.convert("RGB").save(path, "PNG", optimize=True)
        generated.append(path)
        print(f"Saved: {path}")
    sheet_path = output_dir / "contact_sheet_2_panels.jpg"
    make_contact_sheet(generated, sheet_path)
    print(f"Contact sheet: {sheet_path}")
    print("Note: review product identity, visible label accuracy, latency, and fal.ai usage/cost in the dashboard.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
