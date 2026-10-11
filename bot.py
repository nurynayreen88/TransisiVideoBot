"""Telegram slideshow bot: no paid API, FFmpeg required on PATH."""
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get('BOT_TOKEN', '')
MAX_IMAGES = int(os.environ.get('MAX_IMAGES', '5'))
DURATION = int(os.environ.get('VIDEO_SECONDS', '10'))
WIDTH = int(os.environ.get('VIDEO_WIDTH', '480'))
HEIGHT = int(os.environ.get('VIDEO_HEIGHT', '854'))
FPS = int(os.environ.get('VIDEO_FPS', '24'))


def render_video(images: list[Path], output: Path, music: Path | None = None):
    """Produce a crossfaded MP4 with gentle Ken Burns motion."""
    if not images:
        raise ValueError('No images')
    n = len(images)
    # Keep fades short enough for any image count and total duration.
    fade = min(0.5, DURATION / (n * 4)) if n > 1 else 0
    clip_duration = (DURATION + (n - 1) * fade) / n
    frames = max(1, round(clip_duration * FPS))
    with tempfile.TemporaryDirectory(prefix='render_') as td:
        temp = Path(td)
        clips = []
        for i, path in enumerate(images):
            with Image.open(path) as original:
                img = ImageOps.exif_transpose(original).convert('RGB')
                img = ImageOps.fit(img, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
                still = temp / f'still_{i}.jpg'
                img.save(still, quality=90)
            clip = temp / f'clip_{i}.mp4'
            # Alternate zoom in/out; zoompan generates smooth frame-by-frame movement.
            zoom = "min(zoom+0.0008,1.12)" if i % 2 == 0 else "max(1.12-on*0.0008,1.0)"
            vf = (f"zoompan=z='{zoom}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
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
                chains.append(f'{last}[{i}:v]xfade=transition=fade:duration={fade:.4f}:offset={offset:.4f}{label}')
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset(context)
    await update.message.reply_text('🎬 Bot Video Transisi V1\n\nHantar 1–5 gambar sebagai foto, satu demi satu. Hantar audio MP3 jika mahu muzik latar. Kemudian taip /jana.\n\n/periksa — bilangan gambar\n/reset — mula semula')


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ids = context.user_data.setdefault('photos', [])
    if len(ids) >= MAX_IMAGES:
        await update.message.reply_text(f'Maksimum {MAX_IMAGES} gambar. Taip /jana atau /reset.')
        return
    ids.append(update.message.photo[-1].file_id)
    await update.message.reply_text(f'✅ Gambar {len(ids)}/{MAX_IMAGES} diterima. Hantar lagi atau /jana.')


async def audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item = update.message.audio or update.message.document
    if not item or (update.message.document and item.mime_type not in ('audio/mpeg','audio/mp3')):
        return
    if (item.file_size or 0) > 12 * 1024 * 1024:
        await update.message.reply_text('Audio terlalu besar. Maksimum 12 MB.')
        return
    context.user_data['music'] = item.file_id
    await update.message.reply_text('🎵 Muzik disimpan untuk video ini.')


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Gambar: {len(context.user_data.get('photos', []))}/{MAX_IMAGES}. Muzik: {'ya' if context.user_data.get('music') else 'tiada'}. Durasi: {DURATION}s.")


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ids = context.user_data.get('photos', [])
    if not ids:
        await update.message.reply_text('Hantar gambar dahulu.')
        return
    if context.user_data.get('busy'):
        await update.message.reply_text('Video sedang diproses.')
        return
    lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
    if lock.locked():
        await update.message.reply_text('Server sedang menjana video lain. Cuba sebentar lagi.')
        return
    await lock.acquire()
    context.user_data['busy'] = True
    await update.message.reply_text('⏳ Menjana video, sila tunggu...')
    try:
        with tempfile.TemporaryDirectory(prefix='telegram_video_') as td:
            folder = Path(td)
            paths = []
            for i, fid in enumerate(list(ids)):
                p = folder / f'{i}.jpg'
                await (await context.bot.get_file(fid)).download_to_drive(p)
                paths.append(p)
            music = None
            if context.user_data.get('music'):
                music = folder / 'music.mp3'
                await (await context.bot.get_file(context.user_data['music'])).download_to_drive(music)
            result = folder / 'video.mp4'
            await asyncio.to_thread(render_video, paths, result, music)
            with result.open('rb') as f:
                await update.message.reply_video(video=f, caption='🎬 Video transisi siap!', supports_streaming=True,
                                                 read_timeout=120, write_timeout=120)
        reset(context)
    except Exception:
        logging.exception('Video generation failed')
        await update.message.reply_text('❌ Gagal menjana video. Cuba kurangkan gambar atau semak log FFmpeg.')
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
