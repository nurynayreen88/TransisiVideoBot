"""Telegram slideshow bot: no paid API, FFmpeg required on PATH."""
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get('BOT_TOKEN', '')
MAX_IMAGES = int(os.environ.get('MAX_IMAGES', '5'))
DURATION = int(os.environ.get('VIDEO_SECONDS', '10'))
WIDTH = int(os.environ.get('VIDEO_WIDTH', '480'))
HEIGHT = int(os.environ.get('VIDEO_HEIGHT', '854'))
FPS = int(os.environ.get('VIDEO_FPS', '24'))
STYLES = {'cinematic': 'fade', 'hybrid': 'smoothleft', 'morph': 'pixelize'}
MUSIC_CHOICES = ('auto', 'cinematic', 'energetic', 'happy', 'luxury', 'nature', 'beauty', 'none', 'custom')
MUSIC_DIR = Path(__file__).resolve().parent / 'music'

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎬 Jana Video', callback_data='make')],
        [InlineKeyboardButton('🎨 Gaya Video', callback_data='styles'), InlineKeyboardButton('🎵 Muzik', callback_data='music')],
        [InlineKeyboardButton('📋 Semak', callback_data='check'), InlineKeyboardButton('🗑 Mula Semula', callback_data='reset')],
    ])


def style_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✨ Hybrid (disyorkan)', callback_data='style:hybrid')],
        [InlineKeyboardButton('🎥 Cinematic', callback_data='style:cinematic'), InlineKeyboardButton('🌀 Morph', callback_data='style:morph')],
        [InlineKeyboardButton('↩️ Kembali', callback_data='home')],
    ])


def music_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✨ Auto', callback_data='music:auto'), InlineKeyboardButton('🔇 Tanpa Muzik', callback_data='music:none')],
        [InlineKeyboardButton('🎬 Cinematic', callback_data='music:cinematic'), InlineKeyboardButton('⚡ Energetic', callback_data='music:energetic')],
        [InlineKeyboardButton('😊 Happy', callback_data='music:happy'), InlineKeyboardButton('💎 Luxury', callback_data='music:luxury')],
        [InlineKeyboardButton('🌿 Nature', callback_data='music:nature'), InlineKeyboardButton('🌸 Beauty', callback_data='music:beauty')],
        [InlineKeyboardButton('📎 MP3 Sendiri', callback_data='music:custom')],
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
    fade = min(0.7, DURATION / (n * 4)) if n > 1 else 0
    clip_duration = (DURATION + (n - 1) * fade) / n
    frames = max(1, round(clip_duration * FPS))
    with tempfile.TemporaryDirectory(prefix='render_') as td:
        temp = Path(td)
        clips = []
        for i, path in enumerate(images):
            with Image.open(path) as original:
                img = ImageOps.exif_transpose(original).convert('RGB')
                # Preserve framing: modest overscan gives zoompan room to move.
                img = ImageOps.fit(img, (round(WIDTH * 1.12), round(HEIGHT * 1.12)), method=Image.Resampling.LANCZOS)
                still = temp / f'still_{i}.jpg'
                img.save(still, quality=90)
            clip = temp / f'clip_{i}.mp4'
            # Subtle editorial motion: vary direction, keep zoom under 8%.
            # Expressions use the output-frame index 'on'; avoid abrupt jumps.
            progress = f'min(on/{max(frames - 1, 1)},1)'
            if i % 3 == 0:
                zoom = f'1+0.075*{progress}'
                x = '(iw-iw/zoom)/2'
                y = '(ih-ih/zoom)/2'
            elif i % 3 == 1:
                zoom = f'1.075-0.055*{progress}'
                x = f'(iw-iw/zoom)*(0.30+0.40*{progress})'
                y = '(ih-ih/zoom)/2'
            else:
                zoom = f'1.025+0.045*{progress}'
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
                transition = ('fade' if style == 'cinematic' else ('fade' if i % 2 else 'smoothleft') if style == 'hybrid' else 'pixelize')
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('busy'):
        await update.effective_message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    reset(context)
    await update.effective_message.reply_text(
        '🎬 PEMBUAT VIDEO MUDAH\\n\\nHantar 1–5 gambar, kemudian tekan Jana Video.\\n'
        'Gaya Hybrid dan muzik Auto dipilih secara automatik. Boleh juga hantar MP3 sendiri.', reply_markup=main_menu())


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('busy'):
        await update.message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    ids = context.user_data.setdefault('photos', [])
    if len(ids) >= MAX_IMAGES:
        await update.message.reply_text(f'Maksimum {MAX_IMAGES} gambar.', reply_markup=main_menu())
        return
    ids.append(update.message.photo[-1].file_id)
    await update.message.reply_text(f'✅ {len(ids)}/{MAX_IMAGES} gambar diterima. Hantar lagi atau jana video.', reply_markup=main_menu())


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
    await update.message.reply_text('🎵 Muzik diterima.', reply_markup=main_menu())


async def choose_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    style = update.effective_message.text.lstrip('/').split('@')[0].lower()
    context.user_data['style'] = style
    await update.effective_message.reply_text(f'✅ Gaya {style} dipilih.', reply_markup=main_menu())


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Gambar: {len(context.user_data.get('photos', []))}/{MAX_IMAGES} | "
        f"Muzik: {context.user_data.get('music_choice', 'auto')} | "
        f"Gaya: {context.user_data.get('style', 'hybrid')} | {DURATION}s.", reply_markup=main_menu())


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    if action == 'make':
        await generate(update, context)
    elif action == 'music':
        await query.message.reply_text('Pilih muzik latar:', reply_markup=music_menu())
    elif action.startswith('music:'):
        choice = action.split(':', 1)[1]
        if choice in MUSIC_CHOICES:
            context.user_data['music_choice'] = choice
            if choice != 'custom':
                context.user_data['music'] = None
            await query.message.reply_text(('Hantar fail MP3 sekarang.' if choice == 'custom' else f'✅ Muzik {choice} dipilih.'), reply_markup=main_menu())
    elif action == 'styles':
        await query.message.reply_text('Pilih gaya video:', reply_markup=style_menu())
    elif action.startswith('style:'):
        context.user_data['style'] = action.split(':', 1)[1]
        await query.message.reply_text(f"✅ Gaya {context.user_data['style']} dipilih.", reply_markup=main_menu())
    elif action == 'check':
        await status(update, context)
    elif action == 'reset':
        await start(update, context)
    elif action == 'home':
        await query.message.reply_text('Menu utama:', reply_markup=main_menu())


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Hantar gambar atau gunakan butang di bawah.', reply_markup=main_menu())


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    ids = context.user_data.get('photos', [])
    if not ids:
        await message.reply_text('Hantar gambar dahulu.')
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
    app.add_handler(CommandHandler('reset', start))
    app.add_handler(CommandHandler('periksa', status))
    app.add_handler(CommandHandler('jana', generate, block=False))
    for style in STYLES:
        app.add_handler(CommandHandler(style, choose_style))
    app.add_handler(CallbackQueryHandler(buttons, pattern=r'^(make|styles|music|check|reset|home|style:(hybrid|cinematic|morph)|music:(auto|cinematic|energetic|happy|luxury|nature|beauty|none|custom))$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
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
))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
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
))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
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
))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
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
))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
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
))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
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
))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
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
))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
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
