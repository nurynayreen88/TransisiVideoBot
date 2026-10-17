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
from modules.storyboard_engine import (
    StoryboardEngineError, build_storyboard_prompt, generate_storyboard_image, image_api_enabled,
)

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
        "KLIPPO | STORYBOARD IMEJ TUNGGAL (BETA)\n\n"
        "1. Hantar satu gambar produk.\n"
        "2. Pilih tujuan, gaya visual dan latar.\n"
        "3. Terima prompt storyboard dan, jika API imej diaktifkan secara jelas, satu imej 9:16.\n\n"
        "Penjanaan API imej dinyahaktifkan secara lalai untuk mengelakkan caj tanpa kebenaran."
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
        context.user_data.pop("visual_style", None)
        context.user_data.pop("visual_environment", None)
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
    """Route image storyboard to the new flow; preserve the legacy video path."""
    query = update.callback_query
    await query.answer()
    output_format = query.data.split(":", 1)[1]
    if not context.user_data.get("product_image"):
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    if output_format == "image":
        keyboard = [
            [InlineKeyboardButton("📦 Produk Sahaja", callback_data="visual:product_only")],
            [InlineKeyboardButton("🧍 Model Memegang/Memakai", callback_data="visual:model_holding")],
            [InlineKeyboardButton("📸 Model + Produk (Lifestyle)", callback_data="visual:model_lifestyle")],
        ]
        await query.edit_message_text("Pilih gaya visual untuk satu imej storyboard:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if output_format == "video":
        await run_legacy_video(update, context)
        return
    await query.edit_message_text("Pilihan tidak sah. Sila hantar gambar produk semula.")


async def choose_visual_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("product_image"):
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    context.user_data["visual_style"] = query.data.split(":", 1)[1]
    keyboard = [
        [InlineKeyboardButton("🏛️ Studio Premium", callback_data="environment:studio")],
        [InlineKeyboardButton("🏡 Suasana Rumah", callback_data="environment:home")],
        [InlineKeyboardButton("☕ Kafe Moden", callback_data="environment:cafe")],
    ]
    await query.edit_message_text("Pilih latar belakang:", reply_markup=InlineKeyboardMarkup(keyboard))


async def choose_environment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    raw = context.user_data.get("product_image")
    if not raw:
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    user_id = query.from_user.id
    if not claim_user(user_id):
        await query.answer("⏳ Proses anda masih berjalan. Tunggu sehingga selesai.", show_alert=True)
        return
    context.user_data["visual_environment"] = query.data.split(":", 1)[1]
    goal = context.user_data.get("content_goal", "shopee")
    prompt = build_storyboard_prompt(
        goal=goal,
        style=context.user_data.get("visual_style", "product_only"),
        environment=context.user_data["visual_environment"],
    )
    context.user_data["storyboard_prompt"] = prompt
    try:
        await query.edit_message_text("Menyediakan prompt storyboard satu imej…")
        image_sent = False
        if image_api_enabled():
            try:
                image_bytes = await asyncio.to_thread(generate_storyboard_image, raw, prompt)
                image_file = io.BytesIO(image_bytes)
                image_file.name = "KLIPPO_STORYBOARD_9x16.jpg"
                await query.message.reply_photo(
                    photo=image_file,
                    caption="🖼️ Imej storyboard tunggal 9:16 siap. Semak kesamaan produk dengan gambar asal.",
                )
                image_sent = True
            except StoryboardEngineError as exc:
                await query.message.reply_text(str(exc))
        if not image_sent:
            await query.message.reply_text(
                "ℹ️ Imej tidak dijana dalam bot kerana penjanaan API dinyahaktifkan atau tidak berjaya. "
                "Untuk pilihan tanpa caj API bot, buka aplikasi Gemini, lampirkan gambar produk asal "
                "dan tampal prompt di bawah."
            )
        await query.message.reply_text(
            "✨ PROMPT STORYBOARD KLIPPO ✨\n\n" + prompt
            + "\n\nSalin prompt ini dan gunakan bersama gambar produk asal dalam Gemini.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Paparkan prompt untuk disalin", callback_data="prompt:show")],
                [InlineKeyboardButton("🎬 Teruskan ke fungsi video beta", callback_data="legacy:video")],
            ]),
        )
    except Exception:
        logging.exception("Single-image storyboard flow failed")
        await query.message.reply_text("Aliran storyboard gagal. Semak log servis beta.")
    finally:
        release_user(user_id)


async def run_legacy_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Keep the existing fal.ai + video-engine path isolated from image generation."""
    query = update.callback_query
    raw = context.user_data.get("product_image")
    goal = context.user_data.get("content_goal", "shopee")
    if not raw:
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    user_id = query.from_user.id
    if not claim_user(user_id):
        await query.answer("⏳ Proses anda masih berjalan. Tunggu sehingga selesai.", show_alert=True)
        return
    started = time.perf_counter()
    try:
        if not os.environ.get("FAL_KEY", "").strip():
            await query.message.reply_text("Fungsi video lama memerlukan FAL_KEY. Fungsi imej tunggal tidak memerlukannya.")
            return
        await query.edit_message_text("Menganalisis produk dan menyediakan video beta…")
        with tempfile.TemporaryDirectory(prefix="klippo-beta-") as temp:
            root = Path(temp)
            image_path = root / "product_reference.jpg"
            image_path.write_bytes(raw)
            attributes = await asyncio.to_thread(analyze_product, image_path)
            (root / "product_attributes.json").write_text(
                __import__("json").dumps(attributes, ensure_ascii=False, indent=2), encoding="utf-8")
            image_url = await asyncio.to_thread(fal_client.upload_file, str(image_path))
            goal_scene = (
                "Shopee affiliate product showcase, clear product visibility and trustworthy commercial styling."
                if goal == "shopee" else
                "TikTok-style energetic visual hook, dynamic but believable framing; keep the product clearly visible."
            )
            panels = []
            for index, scene in enumerate(SCENES, start=1):
                data, latency = await asyncio.to_thread(
                    generate_panel, image_url, attributes, f"{goal_scene} {scene}", index)
                with Image.open(io.BytesIO(data)) as image:
                    image.verify()
                panels.append(data)
                logging.info("Legacy video panel %s latency %.2fs", index, latency)
            panel_paths = []
            for index, data in enumerate(panels, start=1):
                path = root / f"panel_{index}.jpg"
                path.write_bytes(data)
                panel_paths.append(path)
            voiceover = str(attributes.get("voiceover_ms") or "Lihat produk ini dengan reka bentuk dan perincian yang menarik.")
            video_path = root / "klippo_product_video.mp4"
            await query.message.reply_text("Panel video siap. Sedang menghasilkan video 9:16 dan voiceover Bahasa Melayu…")
            await asyncio.to_thread(create_video, panel_paths, voiceover, video_path)
            with video_path.open("rb") as video_file:
                await query.message.reply_video(
                    video=video_file,
                    caption=f"Video beta 9:16 dengan motion + voiceover. Jumlah masa: {time.perf_counter()-started:.1f}s.",
                    supports_streaming=True,
                )
    except Exception as exc:
        logging.exception("Legacy video beta failed")
        message = str(exc)
        if "401" in message or "403" in message or "FAL_KEY" in message:
            safe = "Permintaan fal.ai ditolak. Semak konfigurasi dan akses model pada servis ujian."
        elif "429" in message:
            safe = "Had permintaan/kredit mungkin dicapai. Semak papan pemuka fal.ai."
        else:
            safe = "Ujian video gagal. Semak log servis beta. Enjin video produksi tidak terjejas."
        await query.message.reply_text(safe)
    finally:
        release_user(user_id)


async def show_prompt_for_copy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-send the full prompt so Telegram users can long-press and copy it."""
    query = update.callback_query
    await query.answer()
    prompt = context.user_data.get("storyboard_prompt")
    if not prompt:
        await query.message.reply_text("Prompt tiada. Sila ulang proses daripada gambar produk.")
        return
    await query.message.reply_text(
        "PROMPT STORYBOARD — TEKAN LAMA UNTUK SALIN\n\n" + prompt
    )


async def legacy_video_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await run_legacy_video(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Hantar gambar produk, kemudian pilih tujuan dan format hasil.")


def main() -> None:
    if not TOKEN:
        raise RuntimeError("FAL_TEST_BOT_TOKEN belum ditetapkan.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(choose_goal, pattern=r"^goal:"))
    app.add_handler(CallbackQueryHandler(choose_format, pattern=r"^format:"))
    app.add_handler(CallbackQueryHandler(choose_visual_style, pattern=r"^visual:"))
    app.add_handler(CallbackQueryHandler(choose_environment, pattern=r"^environment:"))
    app.add_handler(CallbackQueryHandler(legacy_video_button, pattern=r"^legacy:video$"))
    app.add_handler(CallbackQueryHandler(show_prompt_for_copy, pattern=r"^prompt:show$"))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
