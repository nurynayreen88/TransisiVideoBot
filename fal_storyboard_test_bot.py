"""Standalone Telegram beta bot for Gemini + fal.ai storyboard/video tests.

Run only as a separate Render service with a separate Telegram bot token.
Required: FAL_TEST_BOT_TOKEN, FAL_KEY, GEMINI_API_KEY.
"""
import asyncio
import io
import logging
import os
import tempfile
import time
from pathlib import Path

import fal_client
from PIL import Image, ImageDraw, ImageOps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)
from fal_storyboard_test import analyze_product, generate_panel
from modules.video_engine import create_video

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("FAL_TEST_BOT_TOKEN", "").strip()
MODEL = os.environ.get("FAL_STORYBOARD_MODEL", "fal-ai/flux-kontext/dev").strip()
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ACTIVE_USERS: set[int] = set()


def claim_user(user_id: int) -> bool:
    """Atomically claim a user's generation slot within this bot process."""
    if user_id in ACTIVE_USERS:
        return False
    ACTIVE_USERS.add(user_id)
    return True


def release_user(user_id: int) -> None:
    ACTIVE_USERS.discard(user_id)


SCENES = [
    "Opening hero shot: product clearly visible in a tasteful, clean setting, three-quarter view.",
    "Detail shot: closer framing on the same product, showing only real visible details and gentle highlights.",
]


def make_sheet(panel_bytes: list[bytes]) -> bytes:
    cell_w, cell_h, margin, header_h = 540, 720, 12, 42
    sheet = Image.new("RGB", (cell_w * 2 + margin * 3, cell_h + header_h + margin * 2), "#f4f0e9")
    draw = ImageDraw.Draw(sheet)
    for index, data in enumerate(panel_bytes):
        with Image.open(io.BytesIO(data)) as source:
            panel = ImageOps.fit(source.convert("RGB"), (cell_w, cell_h), method=Image.Resampling.LANCZOS)
        x = margin + index * (cell_w + margin)
        draw.text((x + 8, 12), f"PANEL {index + 1}", fill="#242424")
        sheet.paste(panel, (x, header_h))
    output = io.BytesIO()
    sheet.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "KLIPPO | BETA STORYBOARD & VIDEO\n\n"
        "1. Hantar satu gambar produk.\n"
        "2. Pilih tujuan kandungan.\n"
        "3. Pilih hasil gambar storyboard atau video motion + voiceover.\n\n"
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
    status = await message.reply_text("Menerima gambar produk…")
    try:
        tg_file = await photo.get_file()
        raw = bytes(await tg_file.download_as_bytearray())
        if not raw or len(raw) > MAX_UPLOAD_BYTES:
            await status.edit_text("Gambar tidak sah atau terlalu besar.")
            return
        context.user_data["product_image"] = raw
        context.user_data.pop("content_goal", None)
        context.user_data.pop("output_format", None)
        await status.edit_text(
            "Untuk tujuan kandungan apa?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛍️ Shopee Affiliate", callback_data="goal:shopee"),
                InlineKeyboardButton("🎵 TikTok Viral", callback_data="goal:tiktok"),
            ]]),
        )
    except Exception:
        logging.exception("Failed to receive Telegram product photo")
        await status.edit_text("Tidak berjaya menerima gambar. Cuba hantar semula.")


async def choose_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if "product_image" not in context.user_data:
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    context.user_data["content_goal"] = query.data.split(":", 1)[1]
    await query.edit_message_text(
        "Pilih hasil yang mahu dijana:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🖼️ Storyboard Panel (Gambar)", callback_data="format:image"),
        ], [
            InlineKeyboardButton("🎬 Video Motion + Voiceover", callback_data="format:video"),
        ]]),
    )


async def choose_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    raw = context.user_data.get("product_image")
    goal = context.user_data.get("content_goal", "shopee")
    if not raw:
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    user_id = query.from_user.id
    if not claim_user(user_id):
        await query.answer("⏳ Proses anda masih berjalan. Tunggu sehingga selesai.", show_alert=True)
        return
    output_format = query.data.split(":", 1)[1]
    started = time.perf_counter()
    try:
        await query.edit_message_text("Menganalisis produk dengan Gemini dan menyediakan dua panel…")
        with tempfile.TemporaryDirectory(prefix="klippo-beta-") as temp:
            root = Path(temp)
            image_path = root / "product_reference.jpg"
            image_path.write_bytes(raw)
            attributes = await asyncio.to_thread(analyze_product, image_path)
            (root / "product_attributes.json").write_text(
                __import__("json").dumps(attributes, ensure_ascii=False, indent=2), encoding="utf-8")
            image_url = await asyncio.to_thread(fal_client.upload_file, str(image_path))
            panels = []
            timings = []
            goal_scene = (
                "Shopee affiliate product showcase, clear product visibility and trustworthy commercial styling."
                if goal == "shopee" else
                "TikTok-style energetic visual hook, dynamic but believable framing; keep the product clearly visible."
            )
            for index, scene in enumerate(SCENES, start=1):
                data, latency = await asyncio.to_thread(
                    generate_panel, image_url, attributes, f"{goal_scene} {scene}", index)
                with Image.open(io.BytesIO(data)) as image:
                    image.verify()
                panels.append(data)
                timings.append(latency)
                logging.info("Panel %s latency %.2fs", index, latency)

            if output_format == "image":
                await query.message.reply_photo(
                    photo=io.BytesIO(make_sheet(panels)),
                    caption=f"Storyboard 2 panel siap untuk semakan. Jumlah masa: {time.perf_counter()-started:.1f}s. "
                            "Semak kesamaan logo, warna, bentuk dan butiran produk.",
                )
            else:
                panel_paths = []
                for index, data in enumerate(panels, start=1):
                    path = root / f"panel_{index}.jpg"
                    path.write_bytes(data)
                    panel_paths.append(path)
                voiceover = str(attributes.get("voiceover_ms") or
                    "Lihat produk ini dengan reka bentuk dan perincian yang menarik.")
                video_path = root / "klippo_product_video.mp4"
                await query.message.reply_text("Panel siap. Sedang menghasilkan video 9:16 dan voiceover Bahasa Melayu…")
                await asyncio.to_thread(create_video, panel_paths, voiceover, video_path)
                with video_path.open("rb") as video_file:
                    await query.message.reply_video(
                        video=video_file,
                        caption=f"Video beta 9:16 dengan motion + voiceover. Jumlah masa: {time.perf_counter()-started:.1f}s.",
                        supports_streaming=True,
                    )
    except Exception as exc:
        logging.exception("Storyboard/video beta failed")
        message = str(exc)
        if "401" in message or "403" in message or "FAL_KEY" in message:
            safe = "Permintaan fal.ai ditolak. Semak konfigurasi dan akses model pada servis ujian."
        elif "429" in message:
            safe = "Had permintaan/kredit mungkin dicapai. Semak papan pemuka fal.ai."
        else:
            safe = "Ujian gagal. Semak log servis ujian Render. Bot produksi tidak terjejas."
        await query.message.reply_text(safe)
    finally:
        release_user(user_id)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Hantar gambar produk, kemudian pilih tujuan dan format hasil.")


def main() -> None:
    if not TOKEN:
        raise RuntimeError("FAL_TEST_BOT_TOKEN belum ditetapkan.")
    if not os.environ.get("FAL_KEY", "").strip():
        raise RuntimeError("FAL_KEY belum ditetapkan.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(choose_goal, pattern=r"^goal:"))
    app.add_handler(CallbackQueryHandler(choose_format, pattern=r"^format:"))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
