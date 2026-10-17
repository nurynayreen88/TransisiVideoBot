"""Standalone Telegram beta bot for testing fal.ai storyboard panels.

Run as a SEPARATE Render service with a SEPARATE Telegram bot token:
  Start Command: python fal_storyboard_test_bot.py
Required env vars: FAL_TEST_BOT_TOKEN, FAL_KEY
Optional: GEMINI_API_KEY, FAL_STORYBOARD_MODEL

This file is intentionally not imported by bot.py and does not change the live Klippo bot.
"""
import asyncio
import io
import logging
import os
import tempfile
from pathlib import Path

import fal_client
from PIL import Image, ImageDraw, ImageOps
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("FAL_TEST_BOT_TOKEN", "").strip()
MODEL = os.environ.get("FAL_STORYBOARD_MODEL", "fal-ai/flux-kontext/dev").strip()
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def describe_product(image_path: Path) -> str:
    if os.environ.get("GEMINI_API_KEY", "").strip():
        try:
            from gemini_vision import _describe
            text = _describe(image_path.read_bytes())
            if text:
                return text
        except Exception as exc:
            logging.warning("Gemini vision failed (%s); use conservative prompt.", type(exc).__name__)
    return (
        "Use the uploaded photograph as the sole reference. Preserve only directly visible product details. "
        "Do not invent brand names, label text, product specifications, colors, materials, or accessories."
    )


def make_panel(image_url: str, product_details: str, scene: str, panel_number: int) -> bytes:
    prompt = (
        "Edit the supplied reference photograph into ONE realistic product-ad storyboard frame. "
        "The reference image is the source of truth for the product. Preserve its identity, silhouette, "
        "proportions, colors, materials, printed label, logo, pattern and visible accessories as closely as possible. "
        "Do not redesign the product or add text, captions, watermarks, or extra logos. "
        "Create one scene only, no collage, in a vertical 9:16 composition with realistic commercial lighting. "
        f"Verified visual notes: {product_details[:1500]} "
        f"Storyboard panel {panel_number}: {scene}"
    )
    result = fal_client.subscribe(
        MODEL,
        arguments={
            "prompt": prompt,
            "image_url": image_url,
            "num_inference_steps": 28,
            "num_images": 1,
            "output_format": "jpeg",
            "aspect_ratio": "9:16",
        },
        with_logs=False,
        client_timeout=240,
    )
    images = result.get("images") or []
    if not images or not images[0].get("url"):
        raise RuntimeError("fal.ai tidak memulangkan imej panel.")
    import requests
    response = requests.get(images[0]["url"], timeout=60)
    response.raise_for_status()
    return response.content


def make_sheet(panel_bytes: list[bytes]) -> bytes:
    cell_w, cell_h, margin, header_h = 540, 720, 12, 42
    sheet = Image.new("RGB", (cell_w * 2 + margin * 3, cell_h + header_h + margin * 2), "#f4f0e9")
    draw = ImageDraw.Draw(sheet)
    for index, data in enumerate(panel_bytes):
        with Image.open(io.BytesIO(data)) as source:
            panel = source.convert("RGB")
            panel.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
            panel = ImageOps.fit(panel, (cell_w, cell_h), method=Image.Resampling.LANCZOS)
        x = margin + index * (cell_w + margin)
        draw.text((x + 8, 12), f"PANEL {index + 1}", fill="#242424")
        sheet.paste(panel, (x, header_h))
    output = io.BytesIO()
    sheet.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "KLIPPO | UJIAN STORYBOARD FAL.AI\n\n"
        "Hantar satu gambar produk. Bot ujian akan cuba menjana 2 panel dan menyusunnya menjadi satu helaian.\n"
        "Ini bot ujian berasingan; hasil AI mungkin mengubah butiran produk."
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.photo:
        return
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > MAX_UPLOAD_BYTES:
        await message.reply_text("Gambar terlalu besar. Cuba hantar gambar yang lebih kecil.")
        return
    status = await message.reply_text("Menerima gambar… menyediakan ujian 2 panel.")
    try:
        tg_file = await photo.get_file()
        raw = bytes(await tg_file.download_as_bytearray())
        if not raw or len(raw) > MAX_UPLOAD_BYTES:
            await status.edit_text("Gambar tidak sah atau terlalu besar.")
            return
        with tempfile.TemporaryDirectory(prefix="klippo-fal-test-") as temp_dir:
            image_path = Path(temp_dir) / "product_reference.jpg"
            image_path.write_bytes(raw)
            await status.edit_text("Langkah 1/3: menganalisis gambar produk…")
            description = await asyncio.to_thread(describe_product, image_path)
            await status.edit_text("Langkah 2/3: menjana 2 panel melalui fal.ai…")
            image_url = await asyncio.to_thread(fal_client.upload_file, str(image_path))
            scenes = [
                "Opening hero frame: product clearly visible in a tasteful, clean setting, three-quarter view, product remains the main subject.",
                "Detail frame: closer view of the same product, showing only real visible details, with gentle realistic highlights and no invented accessories.",
            ]
            panels = []
            for index, scene in enumerate(scenes, start=1):
                panel = await asyncio.to_thread(make_panel, image_url, description, scene, index)
                with Image.open(io.BytesIO(panel)) as checked:
                    checked.verify()
                panels.append(panel)
            sheet = await asyncio.to_thread(make_sheet, panels)
        await status.edit_text("Langkah 3/3: menghantar hasil untuk semakan…")
        await message.reply_photo(photo=io.BytesIO(sheet), caption="Ujian storyboard 2 panel — semak kesamaan produk dengan gambar asal.")
        await status.delete()
    except Exception as exc:
        logging.exception("fal storyboard test failed")
        safe_error = str(exc)
        if "FAL_KEY" in safe_error or "401" in safe_error or "403" in safe_error:
            user_message = "fal.ai tidak membenarkan permintaan. Semak FAL_KEY dan akses model dalam Render."
        elif "429" in safe_error:
            user_message = "Had permintaan atau kredit fal.ai mungkin telah dicapai. Semak papan pemuka fal.ai."
        else:
            user_message = "Ujian gagal. Semak log servis ujian di Render. Bot utama tidak terjejas."
        try:
            await status.edit_text(user_message)
        except Exception:
            await message.reply_text(user_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Hantar satu gambar produk untuk menghasilkan helaian ujian 2 panel.")


def main() -> None:
    if not TOKEN:
        raise RuntimeError("FAL_TEST_BOT_TOKEN belum ditetapkan.")
    if not os.environ.get("FAL_KEY", "").strip():
        raise RuntimeError("FAL_KEY belum ditetapkan.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
