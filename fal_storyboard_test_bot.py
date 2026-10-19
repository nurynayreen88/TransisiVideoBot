"""Standalone Telegram beta bot for single-image storyboard and legacy video tests.

Run only as a separate Render service with its own Telegram bot token.
Gemini image API generation is disabled unless explicitly opted in.
The legacy video route separately requires FAL_KEY.
"""
import asyncio
import io
import logging
import os
import tempfile
import time
from pathlib import Path

import fal_client
from PIL import Image
from modules.product_video_prompt import build_video_prompts
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)
from fal_storyboard_test import analyze_product, generate_panel
from modules.video_engine import create_video
from modules.storyboard_engine import build_storyboard_prompt

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "KLIPPO | STORYBOARD 4 PANEL (BETA)\n\n"
        "1. Hantar satu gambar produk.\n"
        "2. Pilih tujuan, gaya visual dan latar.\n"
        "3. Terima prompt storyboard 4 panel lengkap dan butang salin prompt.\n\n"
        "Aliran ini menghasilkan teks sahaja dan tidak memanggil API imej berbayar."
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
        context.user_data.pop("storyboard_prompt", None)
        context.user_data.pop("video_prompts", None)
        context.user_data.pop("video_duration", None)
        await status.edit_text(
            "📦 Gambar produk diterima. Pilih laluan Klippo:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Pilihan A: Storyboard 4 Panel (Skrip + Prompt)", callback_data="mode:storyboard")],
                [InlineKeyboardButton("🎬 Pilihan B: Direct Video Prompt", callback_data="mode:video_prompt")],
            ]),
        )
    except Exception:
        logging.exception("Failed to receive Telegram product photo")
        await status.edit_text("Tidak berjaya menerima gambar. Cuba hantar semula.")


async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route uploaded product images to storyboard prompts or direct video prompts."""
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("product_image"):
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    mode = query.data.split(":", 1)[1]
    if mode == "storyboard":
        await query.edit_message_text(
            "Pilih tujuan storyboard:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛍️ Shopee Affiliate", callback_data="goal:shopee"),
                InlineKeyboardButton("🎵 TikTok Viral", callback_data="goal:tiktok"),
            ]]),
        )
        return
    if mode == "video_prompt":
        await query.edit_message_text(
            "Pilih tempoh video. Setiap segmen diberikan sebagai prompt berasingan untuk 10 saat:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 10 saat — 1 prompt", callback_data="duration:10")],
                [InlineKeyboardButton("🎬 20 saat — 2 prompt berasingan", callback_data="duration:20")],
                [InlineKeyboardButton("🎬 30 saat — 3 prompt berasingan", callback_data="duration:30")],
            ]),
        )
        return
    await query.edit_message_text("Pilihan tidak sah. Sila hantar gambar produk semula.")


async def choose_video_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate the requested number of independent 10-second prompts."""
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("product_image"):
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    try:
        duration = int(query.data.split(":", 1)[1])
        campaign = (
            "Shopee affiliate: credible, product-focused presentation"
            if context.user_data.get("content_goal", "shopee") == "shopee"
            else "TikTok: strong visual hook, energetic but believable product presentation"
        )
        prompts = build_video_prompts(duration, campaign=campaign)
    except (ValueError, KeyError):
        await query.edit_message_text("Tempoh video tidak sah. Sila pilih 10, 20 atau 30 saat.")
        return

    context.user_data["video_prompts"] = prompts
    context.user_data["video_duration"] = duration
    await query.edit_message_text(
        f"✅ Video {duration} saat: {len(prompts)} prompt berasingan. "
        "Setiap prompt ialah satu klip 10 saat. Salin dan gunakan setiap prompt secara berasingan."
    )
    for index, prompt in enumerate(prompts, start=1):
        await send_text_chunks(
            query.message,
            f"📋 PROMPT {index}/{len(prompts)} — KLIP 10 SAAT\n\n{prompt}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Paparkan semua prompt semula", callback_data="prompt:video")
            ]]) if index == len(prompts) else None,
        )


async def send_text_chunks(message, text: str, reply_markup=None) -> None:
    """Send long prompt text safely under Telegram's message length limit."""
    limit = 3600
    chunks = []
    remaining = text.strip()
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        await message.reply_text(chunk, reply_markup=markup)


async def choose_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if "product_image" not in context.user_data:
        await query.edit_message_text("Sila hantar gambar produk dahulu.")
        return
    context.user_data["content_goal"] = query.data.split(":", 1)[1]
    await query.edit_message_text(
        "Pilih gaya visual untuk storyboard 4 panel:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Produk Sahaja", callback_data="visual:product_only")],
            [InlineKeyboardButton("🧍 Model Memegang/Memakai", callback_data="visual:model_holding")],
            [InlineKeyboardButton("📸 Model + Produk (Lifestyle)", callback_data="visual:model_lifestyle")],
        ]),
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
        await query.edit_message_text("Pilih gaya visual untuk storyboard 4 panel:", reply_markup=InlineKeyboardMarkup(keyboard))
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
        await query.message.reply_text("⏳ Proses anda masih berjalan. Tunggu sehingga selesai.")
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
        await query.edit_message_text("Menyediakan skrip Bahasa Melayu dan prompt storyboard 4 panel…")
        goal_label = "Shopee Affiliate" if goal == "shopee" else "TikTok Viral"
        environment_label = {
            "studio": "Studio Premium", "home": "Suasana Rumah", "cafe": "Kafe Moden"
        }.get(context.user_data["visual_environment"], "Studio Premium")
        malay_script = (
            "✨ KLIPPO SUPER STORYBOARD — 4 PANEL\n\n"
            f"🎯 Tujuan: {goal_label} | 📍 Latar: {environment_label}\n\n"
            "PANEL 1 — HOOK (0–3s): Perkenalkan produk dengan komposisi yang kuat dan jelas. "
            "Tarik perhatian melalui visual produk, bukan teks tambahan.\n\n"
            "PANEL 2 — DETAIL (3–6s): Dekatkan kamera untuk menunjukkan bentuk, bahan dan ciri "
            "yang benar-benar kelihatan pada gambar rujukan.\n\n"
            "PANEL 3 — LIFESTYLE / PENGGUNAAN (6–9s): Tunjukkan konteks penggunaan yang munasabah "
            "mengikut gaya visual dipilih. Kekalkan produk yang sama dan jangan reka ciri baharu.\n\n"
            "PANEL 4 — HERO / PENUTUP (9–12s): Akhiri dengan paparan produk yang kemas, premium "
            "dan mudah dikenal pasti. Ini ialah pelan visual; bukan video siap.\n\n"
            "Nota: Klippo hanya menyediakan teks. Tiada API imej berbayar dipanggil. Untuk hasil visual, "
            "muat naik gambar produk asal bersama prompt di platform pilihan."
        )
        await query.message.reply_text(malay_script)
        context.user_data["storyboard_prompt"] = prompt
        await send_text_chunks(
            query.message,
            "🎨 AI IMAGE PROMPT (ENGLISH) — READY TO COPY\n\n" + prompt,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 ChatGPT", url="https://chatgpt.com/"),
                 InlineKeyboardButton("🔗 Gemini", url="https://gemini.google.com/")],
                [InlineKeyboardButton("🔗 Microsoft Copilot", url="https://copilot.microsoft.com/"),
                 InlineKeyboardButton("🔗 Bing Image Creator", url="https://www.bing.com/create")],
                [InlineKeyboardButton("🔗 Canva", url="https://www.canva.com/")],
                [InlineKeyboardButton("📋 Paparkan prompt semula", callback_data="prompt:show")],
                [InlineKeyboardButton("🎬 Uji enjin video beta lama", callback_data="legacy:video")],
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
    await send_text_chunks(
        query.message,
        "PROMPT STORYBOARD — TEKAN LAMA UNTUK SALIN\n\n" + prompt
    )


async def legacy_video_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await run_legacy_video(update, context)


async def show_video_prompt_for_copy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    prompts = context.user_data.get("video_prompts")
    if not prompts:
        await query.message.reply_text("Prompt video tiada. Sila muat naik gambar produk dan pilih Direct Video Prompt.")
        return
    for index, prompt in enumerate(prompts, start=1):
        await send_text_chunks(
            query.message,
            f"PROMPT {index}/{len(prompts)} — KLIP 10 SAAT\n\n" + prompt
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Hantar gambar produk, kemudian pilih tujuan dan format hasil.")


def main() -> None:
    if not TOKEN:
        raise RuntimeError("FAL_TEST_BOT_TOKEN belum ditetapkan.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(choose_mode, pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(choose_video_duration, pattern=r"^duration:(10|20|30)$"))
    app.add_handler(CallbackQueryHandler(choose_goal, pattern=r"^goal:"))
    app.add_handler(CallbackQueryHandler(choose_format, pattern=r"^format:"))
    app.add_handler(CallbackQueryHandler(choose_visual_style, pattern=r"^visual:"))
    app.add_handler(CallbackQueryHandler(choose_environment, pattern=r"^environment:"))
    app.add_handler(CallbackQueryHandler(legacy_video_button, pattern=r"^legacy:video$"))
    app.add_handler(CallbackQueryHandler(show_prompt_for_copy, pattern=r"^prompt:show$"))
    app.add_handler(CallbackQueryHandler(show_video_prompt_for_copy, pattern=r"^prompt:video$"))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
