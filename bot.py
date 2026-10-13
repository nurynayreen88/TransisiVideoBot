"""Telegram slideshow bot: no paid API, FFmpeg required on PATH."""
import asyncio
import html
from io import BytesIO
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from video_merge import merge_videos
from fusion_animation import fusion_gif
import klippo_db
from storyboard_engine import build_storyboard, format_storyboard, source_sequence
from storyboard_overlay import apply_overlay
from gemini_vision import describe_photo
from prompt_engine import build_prompt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get('BOT_TOKEN', '')
MAX_IMAGES = int(os.environ.get('MAX_IMAGES', '5'))
DURATION = int(os.environ.get('VIDEO_SECONDS', '10'))
WIDTH = int(os.environ.get('VIDEO_WIDTH', '480'))
HEIGHT = int(os.environ.get('VIDEO_HEIGHT', '854'))
FPS = int(os.environ.get('VIDEO_FPS', '24'))
STYLES = {
    'hybrid': ('smoothleft', 'smoothup', 'fade'),
    'cinematic': ('fade', 'fadeblack'),
    'luxury': ('fadeblack', 'circleopen'),
    'dynamic': ('slideleft', 'slideright', 'slideup'),
    'zoom': ('zoomin', 'circleopen'),
    'smooth': ('smoothleft', 'smoothright', 'smoothup'),
    'creative': ('wipeleft', 'wiperight', 'radial'),
    'morph': ('pixelize', 'circleopen'),
}
STYLE_LABELS = {
    'hybrid': '✨ Hybrid', 'cinematic': '🎥 Cinematic',
    'luxury': '💎 Luxury Reveal', 'dynamic': '⚡ Dynamic',
    'zoom': '🔍 Zoom Reveal', 'smooth': '🌊 Smooth Flow',
    'creative': '🎨 Creative Wipe', 'morph': '🌀 Morph-style',
}
MUSIC_CHOICES = ('auto', 'cinematic', 'energetic', 'happy', 'luxury', 'nature', 'beauty', 'none', 'custom')
MUSIC_DIR = Path(__file__).resolve().parent / 'music'

DOODLE_OPTIONS = {'auto':'✨ Auto', 'white':'🤍 White Doodle', 'sparkle':'✨ Sparkle', 'motion':'🌀 Motion Lines', 'all':'🎨 Gabungan Semua', 'none':'🚫 Tanpa Efek'}
def doodle_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data='doodle:'+key)] for key,label in DOODLE_OPTIONS.items()])

def photos_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📋 Semak Susunan', callback_data='photos_order')],
        [InlineKeyboardButton('↩️ Buang Gambar Terakhir', callback_data='photos_undo')],
        [InlineKeyboardButton('✅ Selesai Hantar Gambar', callback_data='photos_done')],
        [InlineKeyboardButton('🗑 Mula Semula', callback_data='reset')],
    ])


def order_menu(count):
    rows = []
    for i in range(count):
        controls = []
        if i:
            controls.append(InlineKeyboardButton(f'⬆️ {i+1}', callback_data=f'photo_up:{i}'))
        if i < count - 1:
            controls.append(InlineKeyboardButton(f'⬇️ {i+1}', callback_data=f'photo_down:{i}'))
        controls.append(InlineKeyboardButton(f'❌ {i+1}', callback_data=f'photo_remove:{i}'))
        rows.append(controls)
    rows.append([InlineKeyboardButton('📤 Tambah Gambar', callback_data='photos_more'),
                 InlineKeyboardButton('✅ Selesai', callback_data='photos_done')])
    return InlineKeyboardMarkup(rows)


def duration_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⏱️ 10 saat', callback_data='duration:10'),
         InlineKeyboardButton('⏱️ 15 saat', callback_data='duration:15')],
        [InlineKeyboardButton('⏱️ 20 saat', callback_data='duration:20')],
        [InlineKeyboardButton('↩️ Semak Gambar', callback_data='photos_order')],
    ])


def home_keyboard():
    return ReplyKeyboardMarkup([['🏠 Menu Utama']], resize_keyboard=True, is_persistent=True)


def is_admin(user_id):
    return str(user_id) in [x.strip() for x in os.environ.get('ADMIN_USER_IDS', '37141287').split(',')]


def main_menu(user_id=None):
    rows = [
        [InlineKeyboardButton('🎬 Jana Video Transisi', callback_data='make')],
        [InlineKeyboardButton('✍️ Hasilkan Prompt', callback_data='prompt')],
        [InlineKeyboardButton('🎞️ Gabung Video', callback_data='merge')],
        [InlineKeyboardButton('🔄 Tukar Format Video', callback_data='convert')],
        [InlineKeyboardButton('💎 Langganan', callback_data='subscription'), InlineKeyboardButton('👤 Akaun Saya', callback_data='account')],
        [InlineKeyboardButton('❓ Bantuan', callback_data='help')],
    ]
    if user_id is not None and is_admin(user_id):
        rows.append([InlineKeyboardButton('🛡️ Panel Admin', callback_data='admin')])
    return InlineKeyboardMarkup(rows)


def style_menu():
    rows = []
    for key, label in STYLE_LABELS.items():
        rows.append([
            InlineKeyboardButton('▶️ Contoh', callback_data=f'preview:{key}'),
            InlineKeyboardButton(label, callback_data=f'style:{key}'),
        ])
    rows.append([InlineKeyboardButton('↩️ Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def music_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✨ Auto', callback_data='music:auto'), InlineKeyboardButton('🔇 Tanpa Muzik', callback_data='music:none')],
        [InlineKeyboardButton('🎬 Cinematic', callback_data='music:cinematic'), InlineKeyboardButton('⚡ Energetic', callback_data='music:energetic')],
        [InlineKeyboardButton('😊 Happy', callback_data='music:happy'), InlineKeyboardButton('💎 Luxury', callback_data='music:luxury')],
        [InlineKeyboardButton('🌿 Nature', callback_data='music:nature'), InlineKeyboardButton('🌸 Beauty', callback_data='music:beauty')],
        [InlineKeyboardButton('▶️ Dengar Pilihan Muzik', callback_data='music_previews')],
        [InlineKeyboardButton('📎 MP3 Sendiri', callback_data='music:custom')],
        [InlineKeyboardButton('↩️ Tukar Gaya', callback_data='styles')],
    ])


def music_preview_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton('▶️ ' + name.title(), callback_data='listen:' + name)] for name in ('cinematic', 'energetic', 'happy', 'luxury', 'nature', 'beauty')] + [[InlineKeyboardButton('↩️ Pilih Muzik', callback_data='music')]])


def confirm_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Hasilkan Video', callback_data='confirm')],
        [InlineKeyboardButton('🎨 Tukar Gaya', callback_data='styles'), InlineKeyboardButton('🎵 Tukar Muzik', callback_data='music')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def resolve_music(choice: str, style: str) -> Path | None:
    if choice == 'none' or choice == 'custom':
        return None
    name = ({'hybrid': 'happy', 'cinematic': 'cinematic', 'morph': 'energetic'}.get(style, 'happy')
            if choice == 'auto' else choice)
    path = MUSIC_DIR / (name + '.mp3')
    return path if path.is_file() else None


def render_video(images: list[Path], output: Path, music: Path | None = None, style: str = 'hybrid', duration: int = DURATION, doodle: str = 'none'):
    """Produce CPU-friendly Ken Burns transitions. Morph is an approximation, not generative AI."""
    if style not in STYLES:
        raise ValueError("Unknown style")
    if not images:
        raise ValueError('No images')
    n = len(images)
    # Keep fades short enough for any image count and total duration.
    fade = min(0.95, duration / (n * 3.2)) if n > 1 else 0
    clip_duration = (duration + (n - 1) * fade) / n
    frames = max(1, round(clip_duration * FPS))
    with tempfile.TemporaryDirectory(prefix='render_') as td:
        temp = Path(td)
        clips = []
        for i, path in enumerate(images):
            with Image.open(path) as original:
                img = ImageOps.exif_transpose(original).convert('RGB')
                # Preserve framing: modest overscan gives zoompan room to move.
                img = ImageOps.fit(img, (round(WIDTH * 1.22), round(HEIGHT * 1.22)), method=Image.Resampling.LANCZOS)
                still = temp / f'still_{i}.jpg'
                img.save(still, quality=90)
            clip = temp / f'clip_{i}.mp4'
            # Subtle editorial motion: vary direction, limit zoom change to 7.5%.
            # Expressions use the output-frame index 'on'; avoid abrupt jumps.
            progress = f'min(on/{max(frames - 1, 1)},1)'
            if i % 3 == 0:
                zoom = f'1.03+0.075*{progress}'
                x = '(iw-iw/zoom)/2'
                y = '(ih-ih/zoom)/2'
            elif i % 3 == 1:
                zoom = f'1.11-0.075*{progress}'
                x = f'(iw-iw/zoom)*(0.30+0.40*{progress})'
                y = '(ih-ih/zoom)/2'
            else:
                zoom = f'1.04+0.075*{progress}'
                x = '(iw-iw/zoom)/2'
                y = f'(ih-ih/zoom)*(0.65-0.30*{progress})'
            vf = (f"zoompan=z='{zoom}':x='{x}':y='{y}':"
                  f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p")
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-i',str(still),
                   '-vf',vf,'-frames:v',str(frames),'-an','-c:v','libx264',
                   '-preset','veryfast','-crf','25','-pix_fmt','yuv420p',str(clip)]
            subprocess.run(cmd, check=True, timeout=180)
            clips.append(clip)
        if n == 1:
            video = clips[0]
        else:
            video = temp / 'joined.mp4'
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y']
            for clip in clips:
                cmd += ['-i',str(clip)]
            chains = []
            last = '[0:v]'
            for i in range(1,n):
                label = f'[v{i}]'
                offset = i * (clip_duration - fade)
                transition = STYLES[style][(i - 1) % len(STYLES[style])]
                chains.append(f'{last}[{i}:v]xfade=transition={transition}:duration={fade:.4f}:offset={offset:.4f}{label}')
                last = label
            cmd += ['-filter_complex',';'.join(chains),'-map',last,'-an','-c:v','libx264',
                    '-preset','veryfast','-crf','25','-pix_fmt','yuv420p',str(video)]
            subprocess.run(cmd, check=True, timeout=240)
        if doodle != 'none':
            decorated = temp / 'decorated.mp4'
            apply_overlay(video, decorated, doodle, WIDTH, HEIGHT, duration)
            video = decorated
        if music:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),
                            '-stream_loop','-1','-i',str(music),'-map','0:v:0','-map','1:a:0',
                            '-t',str(duration),'-c:v','copy','-c:a','aac','-b:a','128k',
                            '-movflags','+faststart',str(output)],check=True,timeout=180)
        else:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),
                            '-t',str(duration),'-c','copy','-movflags','+faststart',str(output)],
                           check=True,timeout=180)


def reset(context):
    context.user_data['photos'] = []
    context.user_data['music'] = None
    context.user_data['music_choice'] = 'auto'
    context.user_data['style'] = 'hybrid'
    context.user_data['duration'] = 10
    context.user_data['doodle_choice'] = 'none'
    context.user_data['storyboard_mode'] = False
    context.user_data['prompt_mode'] = 'normal'
    context.user_data['prompt_vision'] = ''
    context.user_data['prompt_product'] = ''
    context.user_data['stage'] = 'home'


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text('Akses tidak dibenarkan.')
        return
    if not klippo_db.configured():
        await update.effective_message.reply_text('🛡️ KLIPPO ADMIN\\n\\n⚠️ Sambungan Supabase belum ditetapkan di Render.')
        return
    try:
        pending = await asyncio.to_thread(klippo_db.pending_receipts)
        await update.effective_message.reply_text(
            f'🛡️ KLIPPO ADMIN\\n\\n🧾 Resit menunggu: {len(pending)} (10 terawal dipaparkan)\\n💎 Kelulusan langganan: Manual',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧾 Semak Resit', callback_data='admin_pending')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    except Exception:
        logging.exception('Admin Supabase error')
        await update.effective_message.reply_text('⚠️ Gagal menghubungi database. Semak konfigurasi Supabase di Render.')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('busy'):
        await update.effective_message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    reset(context)
    await update.effective_message.reply_text('🏠 Menu Utama Klippo', reply_markup=home_keyboard())
    await update.effective_message.reply_text('🎬 KLIPPO | Studio Video Affiliate\n\nHasilkan video produk daripada gambar, gabungkan klip mengikut susunan, tukar video kepada format MP4 menegak untuk affiliate, atau sediakan prompt video.\n\n✨ Apa yang boleh dibuat:\n• Jana Video Transisi — jana MP4 daripada gambar, gaya dan muzik.\n• Tukar Format — sediakan video untuk muat naik affiliate.\n• Gabung Video — cantum sehingga 5 klip dengan pilihan transisi.\n• Hasilkan Prompt — pilih Prompt Biasa atau Prompt Storyboard. Gemini membaca gambar jika tersedia; penjanaan video AI dibuat di platform luar.\n\n💎 Langganan: Pelan Penyokong Awal RM5 / 30 hari. Bayar melalui QR DuitNow dan upload resit untuk semakan manual. Pengaktifan bukan automatik.\n\n👇 Pilih fungsi untuk bermula:', reply_markup=main_menu(update.effective_user.id))


async def account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not klippo_db.configured():
        await update.effective_message.reply_text(f'👤 AKAUN SAYA\\n\\nID Telegram: {user_id}\\nStatus langganan belum dapat disemak.')
        return
    try:
        data = await asyncio.to_thread(klippo_db.subscription, user_id)
        status = 'Tiada langganan' if not data else f"{data['status']} (tamat: {data.get('expires_at') or '-'})"
        await update.effective_message.reply_text(f'👤 AKAUN SAYA\\n\\nID Telegram: {user_id}\\nLangganan: {status}')
    except Exception:
        logging.exception('Account lookup failed')
        await update.effective_message.reply_text('⚠️ Status langganan tidak dapat disemak sekarang.')


async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('stage') != 'receipt_upload':
        return
    item = update.message.photo[-1] if update.message.photo else update.message.document
    if not item or (update.message.document and not (
        (item.mime_type or '').startswith('image/') or item.mime_type == 'application/pdf'
    )):
        await update.message.reply_text('Sila hantar gambar atau fail PDF resit.')
        return
    if (item.file_size or 0) > 10 * 1024 * 1024:
        await update.message.reply_text('Resit terlalu besar. Maksimum 10 MB.')
        return
    if not klippo_db.configured():
        await update.message.reply_text('⚠️ Sistem resit belum tersedia. Sila cuba selepas konfigurasi selesai.')
        return
    try:
        receipt = await asyncio.to_thread(klippo_db.submit_receipt,
            update.effective_user.id, update.effective_user.full_name,
            item.file_id, 'photo' if update.message.photo else 'document')
    except Exception:
        logging.exception('Could not save receipt')
        await update.message.reply_text('⚠️ Resit belum berjaya direkodkan. Sila cuba semula.')
        return
    admins = [x.strip() for x in os.environ.get('ADMIN_USER_IDS', '37141287').split(',') if x.strip().isdigit()]
    delivered = False
    for admin_id in admins:
        try:
            await context.bot.send_message(chat_id=int(admin_id), text=(
                f'🧾 RESIT LANGGANAN KLIPPO #{receipt["id"]}\n'
                f'Pengguna: {update.effective_user.full_name}\n'
                f'ID Telegram: {update.effective_user.id}\n'
                'Status: Menunggu semakan manual. Jangan aktifkan tanpa mengesahkan transaksi.'
            ))
            await update.message.forward(chat_id=int(admin_id))
            delivered = True
        except Exception:
            logging.exception('Could not deliver subscription receipt to admin %s', admin_id)
    if delivered:
        context.user_data['stage'] = None
        await update.message.reply_text('🧾 Resit diterima. Status: Dalam semakan.', reply_markup=main_menu())
    else:
        context.user_data['stage'] = None
        await update.message.reply_text(f'🧾 Resit #{receipt["id"]} direkodkan. Status: Dalam semakan. Salinan Telegram kepada admin gagal dihantar; sila hubungi admin untuk semakan.', reply_markup=main_menu())


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('busy'):
        await update.message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    if context.user_data.get('stage') == 'receipt_upload':
        await receive_receipt(update, context)
        return
    if context.user_data.get('stage') == 'prompt_photo':
        context.user_data['prompt_photo_id'] = update.message.photo[-1].file_id
        context.user_data['stage'] = 'prompt_details_choice'
        description = None
        if os.environ.get('GEMINI_API_KEY'):
            try:
                image_file = await context.bot.get_file(context.user_data['prompt_photo_id'])
                image_bytes = bytes(await image_file.download_as_bytearray())
                description = await describe_photo(image_bytes)
            except Exception:
                logging.exception('Product image analysis unavailable')
        context.user_data['prompt_vision'] = description or ''
        await update.message.reply_text(('🔎 AI mengenal pasti: ' + description + '\n\n' if description else '📷 Gambar diterima. AI Vision tidak tersedia; prompt masih boleh digunakan bersama gambar rujukan.\n\n') + 'Mahu tambah maklumat produk secara pilihan?', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✍️ Tambah Maklumat', callback_data='prompt_details:add')], [InlineKeyboardButton('✨ Teruskan Dengan Gambar Sahaja', callback_data='prompt_details:skip')]]))
        return
    if context.user_data.get('stage') != 'photos':
        await update.message.reply_text('Tekan 🎬 Video Transisi dahulu.', reply_markup=main_menu())
        return
    ids = context.user_data.setdefault('photos', [])
    if len(ids) >= MAX_IMAGES:
        await update.message.reply_text(f'Maksimum {MAX_IMAGES} gambar.', reply_markup=photos_menu())
        return
    ids.append(update.message.photo[-1].file_id)
    await update.message.reply_text(f'✅ {len(ids)}/{MAX_IMAGES} gambar diterima. Hantar lagi atau tekan Selesai Hantar Gambar.', reply_markup=photos_menu())


async def audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item = update.message.audio or update.message.document
    if not item or (update.message.document and item.mime_type not in ('audio/mpeg','audio/mp3')):
        return
    if context.user_data.get('busy'):
        await update.message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    if (item.file_size or 0) > 12 * 1024 * 1024:
        await update.message.reply_text('Audio terlalu besar. Maksimum 12 MB.')
        return
    context.user_data['music'] = item.file_id
    context.user_data['music_choice'] = 'custom'
    await update.message.reply_text('🎵 Muzik diterima. Tekan Hasilkan Video.', reply_markup=confirm_menu())


async def choose_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    style = update.effective_message.text.lstrip('/').split('@')[0].lower()
    context.user_data['style'] = style
    await update.effective_message.reply_text(f'✅ Gaya {style} dipilih.', reply_markup=main_menu())


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Gambar: {len(context.user_data.get('photos', []))}/{MAX_IMAGES} | "
        f"Muzik: {context.user_data.get('music_choice', 'auto')} | "
        f"Gaya: {context.user_data.get('style', 'hybrid')} | {context.user_data.get('duration', 10)}s.", reply_markup=main_menu())



def convert_shopee(source: Path, destination: Path):
    """Normalize a source video to a broadly compatible vertical MP4."""
    # Retain native 1080p detail; only upscale smaller portrait sources to 720p.
    dimensions = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=width,height', '-of', 'csv=p=0:s=x', str(source)],
        capture_output=True, text=True, check=True, timeout=20).stdout.strip()
    width, height = map(int, dimensions.split('x'))
    if width <= 0 or height <= 0:
        raise ValueError('Invalid input dimensions')
    if width >= 1080 and height >= 1920:
        target_w, target_h = 1080, 1920
    else:
        target_w, target_h = 720, 1280
    vf = (f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
          f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
          "setsar=1,fps=30,format=yuv420p")
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'a:0',
         '-show_entries', 'stream=index', '-of', 'csv=p=0', str(source)],
        capture_output=True, text=True, check=True, timeout=20)
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source)]
    if probe.stdout.strip():
        cmd += ['-map', '0:v:0', '-map', '0:a:0', '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', '-ac', '2']
    else:
        cmd += ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac', '-b:a', '128k', '-shortest']
    cmd += ['-vf', vf, '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
            '-profile:v', 'high', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', '-max_muxing_queue_size', '1024', str(destination)]
    subprocess.run(cmd, check=True, timeout=240)


async def convert_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('stage') == 'receipt_upload':
        await receive_receipt(update, context)
        return
    if context.user_data.get('stage') == 'merge_upload':
        item = update.message.video or update.message.document
        if not item or (update.message.document and item.mime_type != 'video/mp4'):
            await update.message.reply_text('Sila hantar video MP4.')
            return
        if item.file_size and item.file_size > 19 * 1024 * 1024:
            await update.message.reply_text('Fail melebihi 19 MB.')
            return
        clips = context.user_data.setdefault('merge_files', [])
        if len(clips) >= 5:
            await update.message.reply_text('Maksimum 5 video. Tekan Selesai.')
            return
        clips.append(item.file_id)
        rows = []
        if len(clips) >= 2:
            rows.append([InlineKeyboardButton('✅ Selesai & Pilih Transisi', callback_data='merge_done')])
        if len(clips) < 5:
            message = f'✅ Video {len(clips)} diterima (urutan #{len(clips)}).\\n\\n📤 Terus hantar Video {len(clips) + 1} sebagai File / Document.'
        else:
            message = '✅ Video 5 diterima. Maksimum 5 video. Tekan Selesai untuk pilih transisi.'
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(rows) if rows else None)
        return
    if context.user_data.get('stage') != 'convert':
        await update.message.reply_text('Tekan Tukar Video dahulu.', reply_markup=main_menu())
        return
    if context.user_data.get('busy'):
        await update.message.reply_text('Pemprosesan sedang berjalan.')
        return
    item = update.message.video or update.message.document
    if update.message.video:
        await update.message.reply_text('ℹ️ Video dihantar melalui pilihan Video. Telegram mungkin telah memampatkan fail asal. Untuk kualiti terbaik pada masa depan, gunakan 📎 → File / Fail. Saya akan terus proses video ini.')
    if not item or (update.message.document and item.mime_type != 'video/mp4'):
        await update.message.reply_text('Sila hantar fail MP4.')
        return
    if item.file_size and item.file_size > 19 * 1024 * 1024:
        await update.message.reply_text('Fail melebihi had muat turun bot ini (19 MB). Sila gunakan video lebih kecil.')
        return
    lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
    if lock.locked():
        await update.message.reply_text('Server sedang memproses video lain. Cuba sebentar lagi.')
        return
    async with lock:
        context.user_data['busy'] = True
        try:
            await update.message.reply_text('⏳ Sedang menukar video kepada MP4 mesra Shopee...')
            with tempfile.TemporaryDirectory(prefix='shopee_') as td:
                source = Path(td) / 'input.mp4'
                destination = Path(td) / 'shopee.mp4'
                await (await context.bot.get_file(item.file_id)).download_to_drive(source)
                await asyncio.to_thread(convert_shopee, source, destination)
                with destination.open('rb') as handle:
                    await update.message.reply_document(document=handle, filename='Klippo_Shopee_HQ.mp4', caption='✅ MP4 berkualiti tinggi. Muat turun sebagai fail untuk mengelakkan pemampatan tambahan. Kelulusan Shopee tertakluk pada peraturan platform.', reply_markup=main_menu())
        except Exception:
            logging.exception('Shopee conversion failed')
            await update.message.reply_text('Penukaran gagal. Cuba video MP4 yang lebih pendek atau kecil.', reply_markup=main_menu())
        finally:
            context.user_data['busy'] = False
            context.user_data['stage'] = 'home'


async def generate_merge(update: Update, context: ContextTypes.DEFAULT_TYPE, style: str):
    query = update.callback_query
    lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
    if lock.locked():
        await query.message.reply_text('Server sedang sibuk. Cuba sebentar lagi.')
        return
    async with lock:
        context.user_data['busy'] = True
        animation = None
        success_animation = None
        try:
            try:
                animation = await query.message.reply_animation(animation=fusion_gif(), caption='⏳ Dalam proses...')
            except Exception:
                logging.exception('Fusion animation unavailable')
            with tempfile.TemporaryDirectory(prefix='merge_') as folder:
                paths = []
                for index, file_id in enumerate(context.user_data['merge_files']):
                    path = Path(folder) / f'input_{index}.mp4'
                    await (await context.bot.get_file(file_id)).download_to_drive(path)
                    paths.append(path)
                output = Path(folder) / 'gabungan.mp4'
                await asyncio.to_thread(merge_videos, paths, output, style)
                try:
                    if animation:
                        await animation.delete()
                        animation = None
                    success_animation = await query.message.reply_animation(animation=fusion_gif(True), caption='✅ Gabungan selesai!')
                except Exception:
                    logging.exception('Fusion completion display failed')
                with output.open('rb') as file:
                    await query.message.reply_document(document=file, filename='Klippo_Gabungan.mp4', caption='✅ Video siap digabung. Audio asal dikekalkan dan dipadankan dengan transisi.', reply_markup=main_menu(), write_timeout=240, read_timeout=120, connect_timeout=30)
        except Exception:
            logging.exception('Video merge failed')
            await query.message.reply_text('Gabungan gagal. Cuba klip MP4 lebih pendek.', reply_markup=main_menu())
        finally:
            for item in (animation,):
                if item:
                    try:
                        await item.delete()
                    except Exception:
                        logging.debug('Could not remove temporary animation', exc_info=True)
            context.user_data['busy'] = False
            reset(context)


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    if context.user_data.get('busy'):
        await query.message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    stage = context.user_data.get('stage', 'home')
    if action == 'admin_pending':
        if not is_admin(update.effective_user.id):
            await query.message.reply_text('Akses tidak dibenarkan.')
            return
        try:
            pending = await asyncio.to_thread(klippo_db.pending_receipts)
            if not pending:
                await query.message.reply_text('Tiada resit menunggu.')
            for receipt in pending:
                rid = receipt['id']
                await query.message.reply_text(
                    f"🧾 Resit #{rid}\nPengguna: {receipt.get('telegram_name') or '-'}\nID: {receipt['telegram_user_id']}\nSila semak resit yang dihantar ke chat admin dan pastikan bayaran diterima sebelum meluluskan.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Lulus', callback_data=f'admin_approve:{rid}'), InlineKeyboardButton('❌ Tolak', callback_data=f'admin_reject:{rid}')]]))
        except Exception:
            logging.exception('Pending receipt lookup failed')
            await query.message.reply_text('Gagal mendapatkan resit. Semak sambungan database.')
    elif action.startswith(('admin_approve:', 'admin_reject:')):
        if not is_admin(update.effective_user.id):
            await query.message.reply_text('Akses tidak dibenarkan.')
            return
        approve = action.startswith('admin_approve:')
        rid = int(action.split(':', 1)[1])
        try:
            result = await asyncio.to_thread(klippo_db.review, rid, update.effective_user.id, approve)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"Resit #{rid}: {'Diluluskan' if approve else 'Ditolak'}.")
            try:
                await context.bot.send_message(chat_id=result['user_id'], text=(
                    f"✅ Bayaran disahkan. Langganan Klippo aktif sehingga {result['expiry']}." if approve
                    else '❌ Resit tidak diluluskan. Sila hubungi admin jika pembayaran telah berjaya.'))
            except Exception:
                logging.exception('Could not notify subscriber')
        except Exception:
            logging.exception('Receipt review failed')
            await query.message.reply_text('Gagal memproses resit. Mungkin sudah disemak atau sambungan database bermasalah.')
    elif action == 'admin':
        await admin(update, context)
    elif action == 'storyboard':
        reset(context)
        context.user_data['storyboard_mode'] = True
        context.user_data['stage'] = 'photos'
        await query.message.reply_text('🎞️ STORYBOARD V1 — Hantar 1–5 gambar produk. Bot akan susun enam babak sinematik. Tekan Selesai apabila cukup.', reply_markup=photos_menu())
    elif action == 'make':
        reset(context)
        context.user_data['stage'] = 'photos'
        await query.message.reply_text('Langkah 1/4 — Hantar 1–5 gambar produk. Tekan Selesai apabila cukup.', reply_markup=photos_menu())
    elif action == 'prompt':
        reset(context)
        context.user_data['stage'] = 'prompt_type'
        await query.message.reply_text('✍️ HASILKAN PROMPT — Pilih jenis:', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('✨ Prompt Biasa', callback_data='prompt_type:normal')],
            [InlineKeyboardButton('🎞️ Prompt Storyboard (6 Babak)', callback_data='prompt_type:storyboard')],
            [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
        ]))
    elif action.startswith('prompt_type:') and stage == 'prompt_type':
        context.user_data['prompt_mode'] = action.split(':', 1)[1]
        context.user_data['stage'] = 'prompt_photo'
        await query.message.reply_text('📷 Hantar satu gambar produk. Maklumat tambahan boleh dimasukkan kemudian, tetapi tidak wajib.')
    elif action.startswith('prompt_details:') and stage == 'prompt_details_choice':
        if action == 'prompt_details:add':
            context.user_data['stage'] = 'prompt_details_text'
            await query.message.reply_text('Masukkan maklumat tambahan produk (pilihan), seperti nama atau ciri penting:')
        elif action == 'prompt_details:skip':
            context.user_data['prompt_product'] = ''
            context.user_data['stage'] = 'prompt_scene'
            await query.message.reply_text('Pilih latar atau taip Auto:')
    elif action.startswith('motion:') and stage == 'prompt_motion':
        motion = action.split(':', 1)[1]
        motions = {'orbit': 'A controlled 30-degree camera arc around the product, not a full 360-degree rotation; preserve the visible product geometry.', 'push': 'A slow forward dolly-in with gentle parallax; no object deformation.', 'side': 'A smooth left-to-right camera slide with stable product proportions.', 'static': 'A locked camera with subtle studio lighting changes only.'}
        if motion in motions:
            product = ('the product in the uploaded reference image. Visible observations (verify against reference image): ' + context.user_data.get('prompt_vision', '') + '. Optional user details: ' + context.user_data.get('prompt_product', ''))
            scene = context.user_data.get('prompt_scene', 'clean studio background')
            prompt = build_prompt(context.user_data.get('prompt_mode', 'normal'), product, scene, motion)
            context.user_data['stage'] = 'prompt_done'
            await query.message.reply_text('✅ PROMPT SIAP — gunakan bersama gambar produk. Semak ketepatan pemerhatian AI Vision jika tersedia.')
            # Send a complete downloadable UTF-8 text file for one-step copying.
            mode_name = 'storyboard' if context.user_data.get('prompt_mode') == 'storyboard' else 'biasa'
            prompt_file = BytesIO(prompt.encode('utf-8'))
            prompt_file.name = f'KLIPPO_prompt_{mode_name}.txt'
            await query.message.reply_document(
                document=prompt_file,
                filename=prompt_file.name,
                caption='📋 Prompt penuh dalam satu fail .txt — buka dan salin semuanya tanpa kehilangan bahagian.'
            )
            # Telegram renders <pre> as a copy-friendly block. Split long text safely.
            remaining = prompt
            while remaining:
                if len(remaining) <= 3000:
                    chunk, remaining = remaining, ''
                else:
                    split_at = remaining.rfind('\\n\\n', 0, 3000)
                    if split_at < 1000:
                        split_at = 3000
                    chunk, remaining = remaining[:split_at], remaining[split_at:].lstrip('\\n')
                await query.message.reply_text('<pre>' + html.escape(chunk) + '</pre>', parse_mode='HTML')
            await query.message.reply_text('Pilih tindakan seterusnya:', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🤖 Buka NexaBot', url='https://t.me/aigeneratornexa_bot?start=ref37141287'), InlineKeyboardButton('✨ Buka Gemini', url='https://gemini.google.com/')],
                [InlineKeyboardButton('✍️ Prompt Baharu', callback_data='prompt'), InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
            ]))

    elif action == 'merge':
        reset(context)
        context.user_data['stage'] = 'merge_upload'
        context.user_data['merge_files'] = []
        await query.message.reply_text('🎞️ Hantar Video 1 sebagai fail MP4.\n\nTekan 📎 → File / Fail → pilih video dan hantar.\n\nMaksimum 5 video (19 MB dan 20 saat setiap klip).', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Selesai', callback_data='merge_done')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'merge_next':
        if stage not in ('merge_wait_next', 'merge_upload'):
            await query.message.reply_text('Sila mulakan Gabung Video dahulu.')
            return
        context.user_data['stage'] = 'merge_upload'
        await query.message.reply_text(f"📤 Hantar Video {len(context.user_data.get('merge_files', [])) + 1} sebagai File / Document.")
    elif action == 'merge_done':
        if stage not in ('merge_upload', 'merge_wait_next') or len(context.user_data.get('merge_files', [])) < 2:
            await query.message.reply_text('Hantar sekurang-kurangnya 2 video dahulu.')
            return
        context.user_data['stage'] = 'merge_style'
        await query.message.reply_text('Pilih transisi:', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✨ Fade', callback_data='merge_style:fade'), InlineKeyboardButton('🌊 Smooth', callback_data='merge_style:smoothleft')], [InlineKeyboardButton('⚡ Slide', callback_data='merge_style:slideleft'), InlineKeyboardButton('🔍 Zoom', callback_data='merge_style:zoomin')]]))
    elif action.startswith('merge_style:') and stage == 'merge_style':
        await generate_merge(update, context, action.split(':', 1)[1])
    elif action == 'convert':
        reset(context)
        context.user_data['stage'] = 'convert'
        await query.message.reply_text('🔄 TUKAR FORMAT VIDEO UNTUK AFFILIATE\n\nUntuk kualiti terbaik:\n1. Tekan ikon 📎 di ruang mesej.\n2. Pilih File / Fail (bukan Gallery / Video).\n3. Pilih video MP4 asal dan hantar.\n\nBot akan menukar format secara automatik dan menghantar hasil sebagai fail MP4.\n\nNota: Telegram mungkin memampatkan video yang dihantar melalui Gallery / Video.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'photos_order' and stage in ('photos', 'duration'):
        ids = context.user_data.get('photos', [])
        if not ids:
            await query.message.reply_text('Belum ada gambar. Sila hantar gambar dahulu.', reply_markup=photos_menu())
        else:
            for index, file_id in enumerate(ids, 1):
                await query.message.reply_photo(photo=file_id, caption=f'Gambar {index}')
            await query.message.reply_text('📋 Susunan semasa. Gunakan ⬆️ ⬇️ atau ❌ untuk menyusun:', reply_markup=order_menu(len(ids)))
    elif action == 'photos_undo' and stage == 'photos':
        ids = context.user_data.get('photos', [])
        if ids:
            ids.pop()
        await query.message.reply_text(f'Gambar terakhir dibuang. Baki: {len(ids)}.', reply_markup=photos_menu())
    elif action.startswith(('photo_up:', 'photo_down:', 'photo_remove:')) and stage in ('photos', 'duration'):
        ids = context.user_data.get('photos', [])
        action_type, index_text = action.split(':', 1)
        index = int(index_text)
        if index >= len(ids):
            await query.message.reply_text('Susunan telah berubah. Semak semula.', reply_markup=order_menu(len(ids)))
        else:
            if action_type == 'photo_remove':
                ids.pop(index)
            elif action_type == 'photo_up' and index > 0:
                ids[index-1], ids[index] = ids[index], ids[index-1]
            elif action_type == 'photo_down' and index < len(ids)-1:
                ids[index+1], ids[index] = ids[index], ids[index+1]
            await query.message.reply_text(f'📋 Susunan dikemas kini. {len(ids)} gambar.', reply_markup=order_menu(len(ids)) if ids else photos_menu())
    elif action == 'photos_more' and stage in ('photos', 'duration'):
        context.user_data['stage'] = 'photos'
        await query.message.reply_text('📤 Hantar gambar seterusnya.', reply_markup=photos_menu())
    elif action.startswith('duration:') and stage == 'duration':
        duration = int(action.split(':', 1)[1])
        if duration in (10, 15, 20):
            context.user_data['duration'] = duration
            context.user_data['stage'] = 'style'
            await query.message.reply_text(f'⏱️ {duration} saat dipilih. Pilih gaya:', reply_markup=style_menu())
    elif action == 'photos_done':
        if stage not in ('photos', 'duration') or not context.user_data.get('photos'):
            await query.message.reply_text('Hantar sekurang-kurangnya satu gambar dahulu.', reply_markup=photos_menu())
            return
        context.user_data['stage'] = 'duration'
        await query.message.reply_text('⏱️ Pilih durasi video:', reply_markup=duration_menu())
    elif action == 'styles' and stage in ('style', 'music', 'confirm'):
        context.user_data['stage'] = 'style'
        await query.message.reply_text('Langkah 2/4 — Pilih gaya:', reply_markup=style_menu())
    elif action.startswith('preview:') and stage == 'style':
        chosen = action.split(':', 1)[1]
        if chosen not in STYLES:
            return
        lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
        if lock.locked():
            await query.message.reply_text('Server sedang sibuk. Cuba preview sebentar lagi.')
            return
        async with lock:
            context.user_data['busy'] = True
            try:
                with tempfile.TemporaryDirectory(prefix='preview_') as td:
                    folder = Path(td)
                    paths = []
                    for i, fid in enumerate(context.user_data['photos'][:2]):
                        path = folder / f'{i}.jpg'
                        await (await context.bot.get_file(fid)).download_to_drive(path)
                        paths.append(path)
                    video = folder / 'preview.mp4'
                    await asyncio.to_thread(render_video, paths, video, None, chosen)
                    with video.open('rb') as handle:
                        await query.message.reply_video(video=handle, caption=f'▶️ Contoh {chosen}. Pilih gaya di bawah.', reply_markup=style_menu(), supports_streaming=True)
            except Exception:
                logging.exception('Style preview failed')
                await query.message.reply_text('Preview gagal. Sila pilih gaya atau cuba semula.', reply_markup=style_menu())
            finally:
                context.user_data['busy'] = False
    elif action.startswith('style:') and stage == 'style':
        context.user_data['style'] = action.split(':', 1)[1]
        if context.user_data.get('storyboard_mode'):
            context.user_data['stage'] = 'doodle'
            await query.message.reply_text('Pilih efek garisan / doodle untuk prompt storyboard:', reply_markup=doodle_menu())
        else:
            context.user_data['stage'] = 'music'
            await query.message.reply_text(f"✅ Gaya {context.user_data['style']} dipilih.\\nLangkah 3/4 — Pilih muzik:", reply_markup=music_menu())
    elif action.startswith('doodle:') and stage == 'doodle' and context.user_data.get('storyboard_mode'):
        choice = action.split(':', 1)[1]
        if choice in DOODLE_OPTIONS:
            context.user_data['doodle_choice'] = choice
            context.user_data['stage'] = 'music'
            await query.message.reply_text('✅ Efek untuk storyboard: '+DOODLE_OPTIONS[choice]+'\\nEfek pilihan akan dimasukkan ke dalam MP4.\\nPilih muzik:', reply_markup=music_menu())
    elif action == 'music' and stage in ('music', 'confirm'):
        context.user_data['stage'] = 'music'
        await query.message.reply_text('Langkah 3/4 — Pilih muzik:', reply_markup=music_menu())
    elif action == 'music_previews' and stage == 'music':
        await query.message.reply_text('Tekan untuk mendengar contoh muzik:', reply_markup=music_preview_menu())
    elif action.startswith('listen:') and stage == 'music':
        name = action.split(':', 1)[1]
        if name in MUSIC_CHOICES and name not in ('auto', 'none', 'custom'):
            path = resolve_music(name, context.user_data.get('style', 'hybrid'))
            if path:
                with path.open('rb') as handle:
                    await query.message.reply_audio(audio=handle, title=name.title(), reply_markup=music_preview_menu())
            else:
                await query.message.reply_text('Fail muzik belum tersedia pada server.')
    elif action.startswith('music:') and stage == 'music':
        choice = action.split(':', 1)[1]
        if choice in MUSIC_CHOICES:
            context.user_data['music_choice'] = choice
            if choice != 'custom':
                context.user_data['music'] = None
            context.user_data['stage'] = 'confirm'
            await query.message.reply_text(('Hantar MP3 sendiri, kemudian tekan Hasilkan Video.' if choice == 'custom' else f'✅ Muzik {choice} dipilih.\nLangkah 4/4 — Semak dan hasilkan.'), reply_markup=confirm_menu())
    elif action == 'confirm' and stage == 'confirm':
        await generate(update, context)
    elif action == 'subscription':
        await query.message.reply_text('💎 LANGGANAN KLIPPO\n\nRM5 / 30 hari\nSehingga 30 video sebulan.\n\nBayar melalui QR DuitNow. Selepas pembayaran, upload resit untuk semakan admin.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'subscription_qr':
        qr_path = Path(__file__).resolve().parent / 'klippo_qr.jpg'
        if not qr_path.is_file():
            await query.message.reply_text('QR pembayaran belum tersedia. Sila cuba lagi kemudian.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
        else:
            with qr_path.open('rb') as qr_file:
                await query.message.reply_photo(photo=qr_file, caption='💎 KLIPPO — DuitNow QR\n\nPelan Penyokong Awal: RM5 / 30 hari (sehingga 30 video sebulan).\n\nTekan 📎 Upload Resit selepas pembayaran. Pengaktifan adalah manual selepas semakan.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📎 Upload Resit', callback_data='receipt_upload')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'receipt_upload':
        context.user_data['stage'] = 'receipt_upload'
        await query.message.reply_text('📎 Sila hantar gambar atau fail PDF resit pembayaran di sini.')
    elif action == 'account':
        await account_info(update, context)
    elif action == 'help':
        await query.message.reply_text('❓ CARA GUNA\n\n1. Tekan Jana Video.\n2. Hantar 1–5 gambar, kemudian tekan Selesai.\n3. Lihat contoh dan pilih gaya.\n4. Dengar contoh dan pilih muzik.\n5. Tekan Hasilkan Video.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'check':
        await status(update, context)
    elif action == 'reset':
        await start(update, context)
    elif action == 'home':
        await start(update, context)
    else:
        await query.message.reply_text('Pilihan lama telah tamat. Mulakan semula melalui menu utama.', reply_markup=main_menu())


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stage = context.user_data.get('stage')
    value = update.message.text.strip()
    if value == '🏠 Menu Utama':
        await start(update, context)
        return
    shortcuts = {
        '🎬 Jana Video Affiliate': 'make',
        '🎬 Jana Video Transisi': 'make',
        '🔄 Tukar Format Video': 'convert',
        '✍️ Sediakan Prompt Video': 'prompt',
        '✍️ Hasilkan Prompt': 'prompt',
        '💎 Langganan': 'subscription',
        '👤 Akaun Saya': 'account',
        '❓ Bantuan': 'help',
        '🗑 Mula Semula': 'home',
    }
    if value in shortcuts:
        action = shortcuts[value]
        if action == 'make':
            reset(context)
            context.user_data['stage'] = 'photos'
            await update.message.reply_text('Langkah 1/4 — Hantar 1–5 gambar produk. Tekan Selesai apabila cukup.', reply_markup=photos_menu())
        elif action == 'convert':
            reset(context)
            context.user_data['stage'] = 'convert'
            await update.message.reply_text('🔄 TUKAR FORMAT VIDEO\n\nTekan 📎 → File / Fail → pilih video MP4 asal. Bot akan memprosesnya secara automatik.', reply_markup=main_menu())
        elif action == 'prompt':
            reset(context)
            context.user_data['stage'] = 'prompt_type'
            await update.message.reply_text('✍️ HASILKAN PROMPT — Pilih jenis:', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✨ Prompt Biasa', callback_data='prompt_type:normal')],
                [InlineKeyboardButton('🎞️ Prompt Storyboard (6 Babak)', callback_data='prompt_type:storyboard')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
            ]))
        elif action == 'subscription':
            await update.message.reply_text('💎 LANGGANAN KLIPPO\n\nPelan Penyokong Awal: RM5 / 30 hari, sehingga 30 video sebulan. Pengaktifan manual selepas resit disemak.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')]]))
        elif action == 'account':
            await account_info(update, context)
        elif action == 'help':
            await update.message.reply_text('❓ BANTUAN\n\nJana Video: hantar gambar, pilih gaya dan muzik.\nTukar Format: hantar MP4.\nVideo AI: upload gambar, tambah maklumat jika mahu, kemudian pilih latar dan gerakan kamera. Prompt digunakan bersama gambar di penjana video luar.')
        else:
            await start(update, context)
        return
    if stage == 'prompt_details_text':
        context.user_data['prompt_product'] = value[:600]
        context.user_data['stage'] = 'prompt_scene'
        await update.message.reply_text('Maklumat tambahan disimpan. Pilih latar atau taip Auto:')
    elif stage == 'prompt_scene':
        if len(value) < 5 and value.lower() != 'auto':
            await update.message.reply_text('Nyatakan latar ringkas atau taip Auto.')
            return
        context.user_data['prompt_scene'] = 'clean premium studio background' if value.lower() == 'auto' else value[:400]
        context.user_data['stage'] = 'prompt_motion'
        await update.message.reply_text('Langkah 2/2: Pilih gerakan kamera:', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🔄 Orbit Terkawal', callback_data='motion:orbit')],
            [InlineKeyboardButton('🔍 Zoom Masuk', callback_data='motion:push')],
            [InlineKeyboardButton('↔️ Gerak Sisi', callback_data='motion:side')],
            [InlineKeyboardButton('✨ Studio Statik', callback_data='motion:static')],
        ]))
    else:
        await update.message.reply_text('Gunakan butang menu di bawah.', reply_markup=main_menu())


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    ids = context.user_data.get('photos', [])
    if not ids:
        await message.reply_text('Hantar gambar dahulu.', reply_markup=main_menu())
        return
    if context.user_data.get('busy'):
        await message.reply_text('Video sedang diproses.')
        return
    lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
    if lock.locked():
        await message.reply_text('Server sedang menjana video lain. Cuba sebentar lagi.')
        return
    await lock.acquire()
    context.user_data['busy'] = True
    await message.reply_text('⏳ Menjana video, sila tunggu...')
    try:
        with tempfile.TemporaryDirectory(prefix='telegram_video_') as td:
            folder = Path(td)
            paths = []
            for i, fid in enumerate(list(ids)):
                p = folder / f'{i}.jpg'
                await (await context.bot.get_file(fid)).download_to_drive(p)
                paths.append(p)
            music = None
            if context.user_data.get('music_choice') == 'custom' and context.user_data.get('music'):
                music = folder / 'music.mp3'
                await (await context.bot.get_file(context.user_data['music'])).download_to_drive(music)
            elif context.user_data.get('music_choice') == 'custom':
                await message.reply_text('Sila hantar MP3 sendiri dahulu, atau pilih muzik lain.', reply_markup=music_menu())
                return
            elif context.user_data.get('music_choice', 'auto') != 'none':
                music = resolve_music(context.user_data.get('music_choice', 'auto'), context.user_data.get('style', 'hybrid'))
                if music is None:
                    await message.reply_text('Muzik pilihan belum tersedia pada server. Video akan dijana tanpa muzik.')
            result = folder / 'video.mp4'
            if context.user_data.get('storyboard_mode'):
                plan = build_storyboard(len(paths), context.user_data.get('duration', 10))
                await message.reply_text(format_storyboard(plan) + '\n\nEfek prompt: ' + DOODLE_OPTIONS[context.user_data.get('doodle_choice', 'none')] + '\nArahan AI: Tambah efek pilihan secara halus di luar label dan logo produk. Jangan ubah identiti produk. (Efek overlay turut dirender pada MP4.)')
                paths = [paths[i] for i in source_sequence(plan)]
                selected_style = 'cinematic'
                doodle = context.user_data.get('doodle_choice', 'none')
            else:
                selected_style = context.user_data.get('style', 'hybrid')
                doodle = 'none'
            await asyncio.to_thread(render_video, paths, result, music, selected_style, context.user_data.get('duration', 10), doodle)
            with result.open('rb') as f:
                await message.reply_video(video=f, caption='🎬 Video siap! Hantar gambar baharu untuk video seterusnya.', supports_streaming=True,
                                                 read_timeout=120, write_timeout=120)
        reset(context)
        await message.reply_text('Mahu buat video lagi? Hantar gambar baharu.', reply_markup=main_menu())
    except Exception:
        logging.exception('Video generation failed')
        await message.reply_text('❌ Gagal menjana video. Cuba kurangkan gambar atau semak log FFmpeg.')
    finally:
        context.user_data['busy'] = False
        lock.release()


def main():
    if not TOKEN:
        raise RuntimeError('BOT_TOKEN belum ditetapkan')
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg belum dipasang')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin))
    app.add_handler(CommandHandler('reset', start))
    app.add_handler(CommandHandler('periksa', status))
    app.add_handler(CommandHandler('jana', generate, block=False))
    for style in STYLES:
        app.add_handler(CommandHandler(style, choose_style))
    app.add_handler(CallbackQueryHandler(buttons, pattern=r'^(photos_order|photos_undo|photos_more|photo_up:[0-4]|photo_down:[0-4]|photo_remove:[0-4]|duration:(10|15|20)|admin_pending|admin_approve:[0-9]+|admin_reject:[0-9]+|admin|receipt_upload|subscription_qr|make|storyboard|doodle:(auto|white|sparkle|motion|all|none)|convert|merge|merge_next|merge_done|merge_style:(fade|smoothleft|slideleft|zoomin)|prompt|prompt_type:(normal|storyboard)|prompt_details:(add|skip)|motion:(orbit|push|side|static)|photos_done|confirm|styles|music|music_previews|subscription|account|help|check|reset|home|preview:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|listen:(cinematic|energetic|happy|luxury|nature|beauty)|style:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|music:(auto|cinematic|energetic|happy|luxury|nature|beauty|none|custom))$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.MimeType('application/pdf'), receive_receipt))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.MimeType('video/mp4'), convert_upload))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.MimeType('audio/mpeg'), audio))
    url = os.environ.get('WEBHOOK_URL', '').rstrip('/')
    secret = os.environ.get('WEBHOOK_SECRET', '')
    if not url.startswith('https://') or not secret:
        raise RuntimeError('WEBHOOK_URL (https) dan WEBHOOK_SECRET wajib ditetapkan')
    app.run_webhook(
        listen='0.0.0.0',
        port=int(os.environ.get('PORT', '10000')),
        url_path='telegram',
        webhook_url=url + '/telegram',
        secret_token=secret,
        drop_pending_updates=True,
    )

if __name__ == '__main__':
    main()
