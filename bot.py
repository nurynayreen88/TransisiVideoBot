"""Telegram slideshow bot: no paid API, FFmpeg required on PATH."""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from video_merge import merge_videos
from fusion_animation import fusion_gif
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
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
PROMPT_LIBRARY_PATH = Path(__file__).resolve().parent / 'prompts' / 'prompt_library.json'
try:
    with PROMPT_LIBRARY_PATH.open('r', encoding='utf-8') as handle:
        PROMPT_LIBRARY = json.load(handle)
except (OSError, json.JSONDecodeError):
    logging.exception('Klippo prompt library could not be loaded')
    PROMPT_LIBRARY = {'categories': [], 'prompts': []}
PROMPTS_BY_ID = {item['id']: item for item in PROMPT_LIBRARY.get('prompts', [])}
CATEGORIES_BY_ID = {item['id']: item for item in PROMPT_LIBRARY.get('categories', [])}

def prompt_category_menu():
    rows = []
    categories = PROMPT_LIBRARY.get('categories', [])
    for index in range(0, len(categories), 2):
        pair = categories[index:index + 2]
        rows.append([
            InlineKeyboardButton(f"{item.get('emoji', '🎬')} {item['label']}", callback_data=f"pcat:{item['id']}")
            for item in pair
        ])
    rows.append([InlineKeyboardButton('↩️ Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def prompt_options_menu(category_id: str):
    category = CATEGORIES_BY_ID.get(category_id, {})
    rows = []
    for prompt_id in category.get('prompt_ids', []):
        prompt = PROMPTS_BY_ID.get(prompt_id)
        if prompt:
            rows.append([InlineKeyboardButton(f"🎬 {prompt['label']}", callback_data=f"ptpl:{prompt_id}")])
    rows.append([InlineKeyboardButton('↩️ Tukar Kategori', callback_data='prompt_categories')])
    return InlineKeyboardMarkup(rows)


def photos_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton('✅ Selesai Hantar Gambar', callback_data='photos_done')], [InlineKeyboardButton('🗑 Mula Semula', callback_data='reset')]])


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎬 Jana Video Affiliate', callback_data='make')],
        [InlineKeyboardButton('🔄 Tukar Format Video', callback_data='convert')],
        [InlineKeyboardButton('🎞️ Gabung Video', callback_data='merge')],
        [InlineKeyboardButton('✍️ Sediakan Prompt Video', callback_data='prompt')],
        [InlineKeyboardButton('💎 Langganan', callback_data='subscription'), InlineKeyboardButton('👤 Akaun Saya', callback_data='account')],
        [InlineKeyboardButton('❓ Bantuan', callback_data='help')],
    ])


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


def render_video(images: list[Path], output: Path, music: Path | None = None, style: str = 'hybrid'):
    """Produce CPU-friendly Ken Burns transitions. Morph is an approximation, not generative AI."""
    if style not in STYLES:
        raise ValueError("Unknown style")
    if not images:
        raise ValueError('No images')
    n = len(images)
    # Keep fades short enough for any image count and total duration.
    fade = min(0.95, DURATION / (n * 3.2)) if n > 1 else 0
    clip_duration = (DURATION + (n - 1) * fade) / n
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
            # Subtle editorial motion: vary direction, keep zoom under 8%.
            # Expressions use the output-frame index 'on'; avoid abrupt jumps.
            progress = f'min(on/{max(frames - 1, 1)},1)'
            if i % 3 == 0:
                zoom = f'1.03+0.15*{progress}'
                x = '(iw-iw/zoom)/2'
                y = '(ih-ih/zoom)/2'
            elif i % 3 == 1:
                zoom = f'1.18-0.12*{progress}'
                x = f'(iw-iw/zoom)*(0.30+0.40*{progress})'
                y = '(ih-ih/zoom)/2'
            else:
                zoom = f'1.04+0.12*{progress}'
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
        if music:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),
                            '-stream_loop','-1','-i',str(music),'-map','0:v:0','-map','1:a:0',
                            '-t',str(DURATION),'-c:v','copy','-c:a','aac','-b:a','128k',
                            '-movflags','+faststart',str(output)],check=True,timeout=180)
        else:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),
                            '-t',str(DURATION),'-c','copy','-movflags','+faststart',str(output)],
                           check=True,timeout=180)


def reset(context):
    context.user_data['photos'] = []
    context.user_data['music'] = None
    context.user_data['music_choice'] = 'auto'
    context.user_data['style'] = 'hybrid'
    context.user_data['stage'] = 'home'


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    allowed = os.environ.get('ADMIN_USER_IDS', '37141287').split(',')
    if str(update.effective_user.id) not in [x.strip() for x in allowed]:
        await update.effective_message.reply_text('Akses tidak dibenarkan.')
        return
    await update.effective_message.reply_text('🛡️ KLIPPO ADMIN\\n\\n🎞️ Gabung Video: Aktif\\n🎬 Jana Video: Aktif\\n🔄 Tukar Format: Aktif\\n💎 Langganan: Belum aktif')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('busy'):
        await update.effective_message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    reset(context)
    cleanup = await update.effective_message.reply_text('Menu dikemas kini.', reply_markup=ReplyKeyboardRemove(), disable_notification=True)
    try:
        await cleanup.delete()
    except Exception:
        logging.debug('Unable to delete keyboard cleanup message', exc_info=True)
    await update.effective_message.reply_text('🎬 KLIPPO\nVideo Menarik, Semudah Klik.\n\nPilih fungsi di bawah:', reply_markup=main_menu())


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('busy'):
        await update.message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    if context.user_data.get('stage') == 'prompt_upload':
        photo_item = update.message.photo[-1] if update.message.photo else update.message.document
        context.user_data['prompt_reference_photo'] = photo_item.file_id
        context.user_data['stage'] = 'prompt_category'
        await update.message.reply_text(
            '✅ Gambar produk diterima.\\n\\nLangkah 2/3 — Pilih kategori supaya Klippo memaparkan prompt yang direka khusus untuk produk tersebut:',
            reply_markup=prompt_category_menu()
        )
        return
    if context.user_data.get('stage') != 'photos':
        await update.message.reply_text('Tekan 🎬 Jana Video dahulu.', reply_markup=main_menu())
        return
    ids = context.user_data.setdefault('photos', [])
    if len(ids) >= MAX_IMAGES:
        await update.message.reply_text(f'Maksimum {MAX_IMAGES} gambar.', reply_markup=photos_menu())
        return
    photo_item = update.message.photo[-1] if update.message.photo else update.message.document
    ids.append(photo_item.file_id)
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
        f"Gaya: {context.user_data.get('style', 'hybrid')} | {DURATION}s.", reply_markup=main_menu())



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
        context.user_data['stage'] = 'merge_wait_next'
        rows = []
        if len(clips) < 5:
            rows.append([InlineKeyboardButton(f'➕ Hantar Video {len(clips) + 1}', callback_data='merge_next')])
        if len(clips) >= 2:
            rows.append([InlineKeyboardButton('✅ Selesai & Pilih Transisi', callback_data='merge_done')])
        await update.message.reply_text(f'✅ Video {len(clips)} diterima dan disimpan sebagai urutan #{len(clips)}. Pilih langkah seterusnya.', reply_markup=InlineKeyboardMarkup(rows))
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
                animation = await query.message.reply_animation(animation=fusion_gif(), caption='⚡ Watak Klippo cuba bergabung... tunggu sebentar.')
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
                    success_animation = await query.message.reply_animation(animation=fusion_gif(True))
                    await asyncio.sleep(2)
                except Exception:
                    logging.exception('Fusion completion display failed')
                with output.open('rb') as file:
                    await query.message.reply_document(document=file, filename='Klippo_Gabungan.mp4', caption='✅ Video siap digabung. Audio asal dikekalkan dan dipadankan dengan transisi.', reply_markup=main_menu(), write_timeout=240, read_timeout=120, connect_timeout=30)
                if success_animation:
                    try:
                        await success_animation.delete()
                        success_animation = None
                    except Exception:
                        logging.debug('Could not remove success animation', exc_info=True)
        except Exception:
            logging.exception('Video merge failed')
            await query.message.reply_text('Gabungan gagal. Cuba klip MP4 lebih pendek.', reply_markup=main_menu())
        finally:
            for item in (animation, success_animation):
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
    if action == 'make':
        reset(context)
        context.user_data['stage'] = 'photos'
        await query.message.reply_text('Langkah 1/4 — Hantar 1–5 gambar produk. Tekan Selesai apabila cukup.', reply_markup=photos_menu())
    elif action == 'prompt':
        reset(context)
        context.user_data['stage'] = 'prompt_upload'
        await query.message.reply_text('✍️ PROMPT VIDEO AFFILIATE\n\nLangkah 1/3 — Upload satu gambar produk yang akan digunakan sebagai rujukan utama di Gemini. Selepas gambar diterima, pilih kategori dan gaya prompt yang sesuai.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'prompt_categories' and stage in ('prompt_category', 'prompt_template', 'prompt_done'):
        context.user_data['stage'] = 'prompt_category'
        await query.message.reply_text('Pilih kategori produk:', reply_markup=prompt_category_menu())
    elif action.startswith('pcat:') and stage in ('prompt_category', 'prompt_template', 'prompt_done'):
        category_id = action.split(':', 1)[1]
        category = CATEGORIES_BY_ID.get(category_id)
        if not category:
            await query.message.reply_text('Kategori tidak ditemui. Sila pilih semula.', reply_markup=prompt_category_menu())
            return
        context.user_data['prompt_category'] = category_id
        context.user_data['stage'] = 'prompt_template'
        await query.message.reply_text(
            f"{category.get('emoji', '🎬')} {category['label']} — pilih gaya video:",
            reply_markup=prompt_options_menu(category_id)
        )
    elif action.startswith('ptpl:') and stage in ('prompt_template', 'prompt_done'):
        prompt_id = action.split(':', 1)[1]
        prompt = PROMPTS_BY_ID.get(prompt_id)
        if not prompt or prompt.get('category') != context.user_data.get('prompt_category'):
            await query.message.reply_text('Prompt tidak sepadan dengan kategori. Sila pilih semula.', reply_markup=prompt_options_menu(context.user_data.get('prompt_category', '')))
            return
        context.user_data['stage'] = 'prompt_done'
        await query.message.reply_text(
            f"✅ PROMPT SIAP — {prompt['label']}\n\nSalin keseluruhan prompt di bawah dan gunakan bersama gambar produk asal di Gemini:\n\n{prompt['prompt']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✨ Buka Gemini', url='https://gemini.google.com/')],
                [InlineKeyboardButton('🔁 Pilih Gaya Lain', callback_data=f"pcat:{prompt['category']}")],
                [InlineKeyboardButton('↩️ Tukar Kategori', callback_data='prompt_categories')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
            ])
        )
    elif action.startswith('motion:') and stage == 'prompt_motion':
        motion = action.split(':', 1)[1]
        motions = {'orbit': 'A controlled 30-degree camera arc around the product, not a full 360-degree rotation; preserve the visible product geometry.', 'push': 'A slow forward dolly-in with gentle parallax; no object deformation.', 'side': 'A smooth left-to-right camera slide with stable product proportions.', 'static': 'A locked camera with subtle studio lighting changes only.'}
        if motion in motions:
            product = context.user_data.get('prompt_product', 'the reference product')
            scene = context.user_data.get('prompt_scene', 'clean studio background')
            prompt = (f'Create a 10-second vertical 9:16 product affiliate video. PRODUCT REFERENCE: {product}. '
                      f'SCENE: {scene}. CAMERA: {motions[motion]} '
                      'Use the uploaded product image as the strict visual reference. Keep the exact identity, shape, color, proportions, branding, labels and number of parts unchanged throughout every frame. '
                      'The product remains the hero, fully visible and sharply focused. Use realistic lighting and smooth physically plausible movement. '
                      'Do not invent extra accessories, alter text or logos, morph the object, duplicate it, introduce people or hands, add captions, watermarks or UI. '
                      'If unseen sides of the product are not provided, do not fabricate them; use only a modest camera arc. No abrupt cuts or flicker. Output 10 seconds, portrait 9:16, high quality.')
            context.user_data['stage'] = 'prompt_done'
            await query.message.reply_text('✅ PROMPT SIAP (salin teks di bawah):\n\n' + prompt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🤖 Buka NexaBot', url='https://t.me/aigeneratornexa_bot?start=ref37141287'), InlineKeyboardButton('✨ Buka Gemini', url='https://gemini.google.com/')], [InlineKeyboardButton('✍️ Prompt Baharu', callback_data='prompt'), InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'merge':
        reset(context)
        context.user_data['stage'] = 'merge_upload'
        context.user_data['merge_files'] = []
        await query.message.reply_text('🎞️ Hantar Video 1 dahulu sebagai MP4. Selepas diterima, tekan Hantar Video 2 dan seterusnya. Maksimum 5 video, 19 MB dan 20 saat setiap klip. Audio asal dikekalkan.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Selesai', callback_data='merge_done')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'merge_next':
        if stage != 'merge_wait_next':
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
    elif action == 'photos_done':
        if stage != 'photos' or not context.user_data.get('photos'):
            await query.message.reply_text('Hantar sekurang-kurangnya satu gambar dahulu.', reply_markup=photos_menu())
            return
        context.user_data['stage'] = 'style'
        await query.message.reply_text('Langkah 2/4 — Lihat contoh dan pilih gaya:', reply_markup=style_menu())
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
        context.user_data['stage'] = 'music'
        await query.message.reply_text(f"✅ Gaya {context.user_data['style']} dipilih.\nLangkah 3/4 — Pilih muzik:", reply_markup=music_menu())
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
        await query.message.reply_text('💎 LANGGANAN KLIPPO\n\nCadangan pelan Penyokong Awal: RM5 / 30 hari, sehingga 30 video sebulan.\n\nPembayaran dan pengaktifan VIP belum dibuka. Kami tidak akan meminta bayaran sebelum fungsi langganan siap.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'account':
        await query.message.reply_text(f'👤 AKAUN SAYA\n\nID Telegram: {query.from_user.id}\nStatus: Akses percubaan (langganan belum diaktifkan).', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📋 Semak Bahan', callback_data='check'), InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
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
    shortcuts = {
        '🎬 Jana Video Affiliate': 'make',
        '🔄 Tukar Format Video': 'convert',
        '✍️ Sediakan Prompt Video': 'prompt',
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
            context.user_data['stage'] = 'prompt_upload'
            await update.message.reply_text('✍️ PROMPT VIDEO AFFILIATE\n\nLangkah 1/3 — Upload satu gambar produk sebagai rujukan utama. Selepas itu, pilih kategori dan gaya prompt yang sesuai.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
        elif action == 'subscription':
            await update.message.reply_text('💎 LANGGANAN\n\nPelan RM5 / 30 hari masih cadangan. Pembayaran belum diaktifkan.')
        elif action == 'account':
            await update.message.reply_text(f'👤 AKAUN SAYA\n\nID Telegram: {update.effective_user.id}\nLangganan belum diaktifkan.')
        elif action == 'help':
            await update.message.reply_text('❓ BANTUAN\n\nJana Video: hantar gambar, pilih gaya dan muzik.\nTukar Format: hantar MP4.\nPrompt: terangkan produk dan pilih gerakan kamera.')
        else:
            await start(update, context)
        return
    if stage == 'prompt_product':
        if len(value) < 8:
            await update.message.reply_text('Sila beri penerangan produk yang lebih khusus (sekurang-kurangnya 8 aksara).')
            return
        context.user_data['prompt_product'] = value[:600]
        context.user_data['stage'] = 'prompt_scene'
        await update.message.reply_text('Langkah 2/3: Nyatakan latar dan suasana yang dikehendaki. Contoh: meja marmar putih, cahaya studio lembut, latar premium tanpa manusia.')
    elif stage == 'prompt_scene':
        if len(value) < 5:
            await update.message.reply_text('Sila terangkan latar dengan lebih jelas.')
            return
        context.user_data['prompt_scene'] = value[:400]
        context.user_data['stage'] = 'prompt_motion'
        await update.message.reply_text('Langkah 3/3: Pilih gerakan kamera:', reply_markup=InlineKeyboardMarkup([
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
            await asyncio.to_thread(render_video, paths, result, music, context.user_data.get('style', 'hybrid'))
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
    app.add_handler(CallbackQueryHandler(buttons, pattern=r'^(make|convert|merge|merge_next|merge_done|merge_style:(fade|smoothleft|slideleft|zoomin)|prompt|prompt_categories|pcat:(clothing|bags|shoes|beauty|gadgets|home)|ptpl:[a-z0-9_]+|motion:(orbit|push|side|static)|photos_done|confirm|styles|music|music_previews|subscription|account|help|check|reset|home|preview:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|listen:(cinematic|energetic|happy|luxury|nature|beauty)|style:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|music:(auto|cinematic|energetic|happy|luxury|nature|beauty|none|custom))$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, photo))
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
