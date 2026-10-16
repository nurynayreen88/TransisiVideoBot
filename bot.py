"""Telegram slideshow bot: no paid API, FFmpeg required on PATH."""
import asyncio
import html
import json
from io import BytesIO
import logging
import os
import re
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, ImageDraw, ImageFont
from video_merge import merge_videos
from fusion_animation import fusion_gif
import klippo_db
from storyboard_engine import build_storyboard, format_storyboard, source_sequence
from storyboard_overlay import apply_overlay, make_handwriting_labels
from gemini_vision import describe_photo
from prompt_engine import build_prompt
from prompt_catalog import choices as storyboard_styles

# Curated prompt library; kept separate from the existing video-generation engine.
PROMPT_LIBRARY_PATH = Path(__file__).resolve().parent / 'prompts' / 'prompt_library.json'
try:
    with PROMPT_LIBRARY_PATH.open('r', encoding='utf-8') as handle:
        PROMPT_LIBRARY = json.load(handle)
except (OSError, json.JSONDecodeError):
    logging.exception('Klippo prompt library could not be loaded')
    PROMPT_LIBRARY = {'categories': [], 'prompts': []}
PROMPTS_BY_ID = {item['id']: item for item in PROMPT_LIBRARY.get('prompts', []) if isinstance(item, dict) and item.get('id')}
CATEGORIES_BY_ID = {item['id']: item for item in PROMPT_LIBRARY.get('categories', []) if isinstance(item, dict) and item.get('id')}
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
# Background engine is bundled here so single-file Render deployments work.
from collections import deque
from io import BytesIO
import os
import logging
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter, ImageDraw

BACKGROUNDS = {
    'white': (250, 250, 248),
    'beige': (225, 209, 187),
    'dark': (33, 34, 41),
    'pastel': (237, 218, 228),
}


def _plain_background_mask(image):
    """Flood-fill edge-connected pixels close to the corner background colour."""
    sample = image.copy()
    sample.thumbnail((480, 480), Image.Resampling.LANCZOS)
    sample = sample.convert('RGB')
    w, h = sample.size
    corners = [sample.getpixel(p) for p in ((0, 0), (w-1, 0), (0, h-1), (w-1, h-1))]
    spread = max(max(c[k] for c in corners)-min(c[k] for c in corners) for k in range(3))
    if spread > 35:
        raise ValueError('Complex or inconsistent background; segmentation model needed')
    bg = tuple(sum(c[k] for c in corners)//4 for k in range(3))
    pix = sample.load()
    visited = bytearray(w*h)
    background_pixels = bytearray(w*h)
    queue = deque()
    for x in range(w):
        queue.append((x, 0)); queue.append((x, h-1))
    for y in range(h):
        queue.append((0, y)); queue.append((w-1, y))
    while queue:
        x, y = queue.popleft()
        pos = y*w+x
        if visited[pos]:
            continue
        visited[pos] = 1
        rgb = pix[x, y]
        if max(abs(rgb[k]-bg[k]) for k in range(3)) > 43:
            continue
        background_pixels[pos] = 1
        for xx, yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= xx < w and 0 <= yy < h and not visited[yy*w+xx]:
                queue.append((xx, yy))
    mask = Image.new('L', (w, h))
    mask.putdata([0 if background_pixels[y*w+x] else 255
                  for y in range(h) for x in range(w)])
    bbox = mask.getbbox()
    if not bbox or bbox[0] == 0 or bbox[1] == 0 or bbox[2] == w or bbox[3] == h:
        raise ValueError('Product touches the image boundary or segmentation uncertain')
    area = sum(v > 127 for v in mask.getdata()) / (w*h)
    if not .025 <= area <= .85:
        raise ValueError('Uncertain product area')
    return mask.resize(image.size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(0.65))


def _remove_bg_api(image):
    """Use the optional remove.bg API key, never store it in source control."""
    import requests
    key = os.environ.get('REMOVE_BG_API_KEY', '').strip()
    if not key:
        return None
    upload = BytesIO()
    image.save(upload, format='PNG')
    try:
        response = requests.post(
            'https://api.remove.bg/v1.0/removebg',
            headers={'X-Api-Key': key},
            files={'image_file': ('product.png', upload.getvalue(), 'image/png')},
            data={'size': 'preview', 'format': 'png'},
            timeout=65,
        )
    except requests.RequestException as exc:
        raise ValueError('remove.bg tidak dapat dihubungi; cuba lagi kemudian') from exc
    if response.status_code != 200:
        logging.warning('remove.bg returned HTTP %s', response.status_code)
        raise ValueError('remove.bg gagal atau kuota API habis (HTTP %s)' % response.status_code)
    try:
        with Image.open(BytesIO(response.content)) as result:
            foreground = result.convert('RGBA')
            foreground.load()
    except Exception as exc:
        raise ValueError('remove.bg tidak memulangkan imej yang sah') from exc
    if not foreground.getchannel('A').getbbox():
        raise ValueError('Tiada produk dikesan oleh remove.bg')
    return foreground


def _scene_background(size, choice):
    """Minimal studio backgrounds; no rooms, logos, labels or text."""
    w, h = size
    palettes = {
        'gradient': ((251, 248, 241), (221, 205, 184)),
        'pattern': ((248, 246, 242), (229, 223, 214)),
        'duotone': ((241, 232, 219), (210, 190, 171)),
        'mist': ((246, 247, 248), (210, 216, 221)),
    }
    top, bottom = palettes[choice]
    canvas = Image.new('RGBA', size)
    draw = ImageDraw.Draw(canvas)
    for y in range(h):
        t = y / max(1, h - 1)
        if choice == 'duotone':
            t = 0 if t < .62 else 1
        color = tuple(round(top[k] * (1 - t) + bottom[k] * t) for k in range(3))
        draw.line((0, y, w, y), fill=color + (255,))
    if choice == 'pattern':
        ink = (224, 216, 205, 255)
        step = max(48, w // 5)
        for x in range(-step, w + step, step):
            for y in range(-step, h + step, step):
                radius = max(7, step // 6)
                draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline=ink, width=max(1,w//400))
    return canvas


def replace_background(source: Path, destination: Path, choice: str, foreground_destination: Path | None = None) -> Path:
    if choice not in BACKGROUNDS and choice not in ('gradient', 'pattern', 'duotone', 'mist'):
        raise ValueError('Unknown background')
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGB')
    foreground = _remove_bg_api(image)
    # Use an installed segmentation model where available, without requiring
    # an external paid API or silently downloading one during every request.
    if foreground is None:
        try:
            from rembg import remove
        except ImportError:
            mask = _plain_background_mask(image)
            foreground = image.convert('RGBA')
            foreground.putalpha(mask)
        else:
            foreground = remove(image).convert('RGBA')
            alpha = foreground.getchannel('A')
            if not alpha.getbbox():
                raise ValueError('No product detected')
    background = (_scene_background(foreground.size, choice) if choice not in BACKGROUNDS
                  else Image.new('RGBA', foreground.size, BACKGROUNDS[choice] + (255,)))
    if foreground_destination is not None:
        foreground.save(foreground_destination, 'PNG')
    background.alpha_composite(foreground)
    background.convert('RGB').save(destination, 'PNG')
    return destination

TOKEN = os.environ.get('BOT_TOKEN', '')
MAX_IMAGES = int(os.environ.get('MAX_IMAGES', '5'))
DURATION = int(os.environ.get('VIDEO_SECONDS', '10'))
# Conservative defaults for Render free-tier RAM; override with env vars if capacity allows.
WIDTH = max(240, min(720, int(os.environ.get('VIDEO_WIDTH', '360'))))
WIDTH -= WIDTH % 2
HEIGHT = max(426, min(1280, int(os.environ.get('VIDEO_HEIGHT', '640'))))
HEIGHT -= HEIGHT % 2
FPS = max(15, min(30, int(os.environ.get('VIDEO_FPS', '20'))))
STYLES = {
    'hybrid': ('smoothleft', 'smoothup', 'fade'),
    'cinematic': ('fade', 'fadeblack'),
    'luxury': ('fadeblack', 'circleopen'),
    'dynamic': ('smoothleft', 'slideleft', 'fade'),
    'zoom': ('zoomin', 'circleopen'),
    'smooth': ('fade', 'fadeblack', 'fade'),
    'creative': ('wipeleft', 'wiperight', 'radial'),
    'morph': ('pixelize', 'circleopen'),
}
STYLE_LABELS = {
    'hybrid': '✨ Hybrid', 'cinematic': '🎥 Cinematic',
    'luxury': '💎 Luxury Reveal', 'dynamic': '⚡ Dynamic',
    'zoom': '🔍 Zoom Reveal', 'smooth': '🌊 Smooth Flow',
    'creative': '🎨 Creative Wipe', 'morph': '🌀 Morph-style',
}
MUSIC_CHOICES = ('auto', 'custom')
MUSIC_DIR = Path(__file__).resolve().parent / 'music'

DOODLE_OPTIONS = {'auto':'✨ Auto (Ikut Latar)', 'black':'🖤 Hitam', 'white':'🤍 Putih', 'gold':'🟡 Emas', 'pastel':'🌸 Pastel', 'sparkle':'✨ Sparkle', 'motion':'🌀 Motion Lines', 'circle':'◯ Circle Highlight', 'pop':'✳️ Pop Burst', 'all':'🎨 Gabungan Semua', 'none':'🚫 Tanpa Efek'}
def doodle_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data='doodle:'+key)] for key,label in DOODLE_OPTIONS.items()])

PRODUCT_TYPES = {
    'fashion': '👗 Pakaian / Fesyen',
    'bag': '👜 Beg / Dompet — auto kesan daripada nama',
    'hijab': '🧕 Tudung / Hijab',
    'shoes': '👟 Kasut',
    'beauty': '💄 Kecantikan / Skincare',
    'food': '🍰 Makanan / Minuman',
    'gadget': '📱 Gajet / Elektronik',
    'home': '🏡 Rumah / Dapur',
    'accessory': '⌚ Aksesori / Barang Kemas',
    'other': '📦 Produk Lain / Auto',
}

def detect_bag_subtype(product_name: str) -> str:
    """Infer bag/wallet subtype from product name only; no image or AI call."""
    name = (product_name or '').casefold()
    if any(k in name for k in ('wallet', 'dompet', 'card holder', 'cardholder', 'coin purse', 'purse kecil', 'money clip')):
        return 'wallet'
    if any(k in name for k in ('backpack', 'back pack', 'beg galas', 'beg sekolah', 'beg laptop', 'rucksack')):
        return 'backpack'
    if any(k in name for k in ('sling bag', 'sling shoulder', 'shoulder sling', 'shoulder sling bag', 'crossbody', 'cross-body', 'beg silang', 'beg sandang')):
        return 'sling_bag'
    if any(k in name for k in ('handbag', 'hand bag', 'beg tangan', 'shoulder bag', 'tote bag', 'tote', 'top handle')):
        return 'handbag'
    if any(k in name for k in ('bag', 'beg', 'purse')):
        return 'bag'
    return ''


def detect_prompt_library_category(product_name: str) -> str:
    subtype = detect_bag_subtype(product_name)
    if subtype == 'wallet':
        return 'wallets'
    if subtype in ('backpack', 'sling_bag', 'handbag', 'bag'):
        return 'bags'
    return ''


def prompt_product_type_menu():
    items = list(PRODUCT_TYPES.items())
    rows = []
    for index in range(0, len(items), 2):
        pair = items[index:index + 2]
        rows.append([InlineKeyboardButton(label, callback_data='prompt_product_type:' + key) for key, label in pair])
    rows.append([InlineKeyboardButton('↩️ Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def prompt_duration_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎬 10 Saat', callback_data='prompt_duration:10'),
         InlineKeyboardButton('🎞️ 20 Saat', callback_data='prompt_duration:20')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


# Keep the style picker relevant to the selected product instead of showing
# unrelated options (for example, Mirror Selfie for a food product).
PRODUCT_STYLE_KEYS = {
    'fashion': {'mirror_selfie', 'fashion_editorial', 'golden_hour', 'lifestyle', 'ugc_review', 'dynamic', 'fast_cut', 'reaction_hook', 'creative_reveal', 'white_doodle', 'cinematic', 'luxury', 'minimal', 'playful_viral', 'studio_360_safe'},
    'bag': {'handbag_showcase', 'bag_detail_macro', 'bag_flatlay', 'bag_daily_carry', 'bag_tabletop_reveal', 'sling_bag_lifestyle', 'backpack_demo', 'wallet_luxury_macro', 'wallet_open_close', 'wallet_daily_carry', 'wallet_flatlay', 'wallet_gift_reveal', 'luxury', 'flatlay', 'unboxing', 'lifestyle', 'ugc_review', 'studio_360_safe', 'creative_reveal', 'fast_cut', 'white_doodle', 'cinematic', 'minimal', 'dynamic'},
    'wallet': {'wallet_luxury_macro', 'wallet_open_close', 'wallet_daily_carry', 'wallet_flatlay', 'wallet_gift_reveal', 'luxury', 'flatlay', 'unboxing', 'studio_360_safe', 'minimal', 'cinematic'},
    'hijab': {'mirror_selfie', 'fashion_editorial', 'golden_hour', 'lifestyle', 'ugc_review', 'dynamic', 'fast_cut', 'reaction_hook', 'creative_reveal', 'white_doodle', 'cinematic', 'luxury', 'minimal'},
    'shoes': {'dynamic', 'fast_cut', 'pov_demo', 'studio_360_safe', 'lifestyle', 'ugc_review', 'creative_reveal', 'white_doodle', 'cinematic', 'minimal', 'playful_viral'},
    'beauty': {'beauty_macro', 'ugc_review', 'luxury', 'cinematic', 'white_doodle', 'minimal', 'fast_cut', 'creative_reveal', 'lifestyle', 'flatlay', 'unboxing'},
    'food': {'food_appetite', 'flatlay', 'lifestyle', 'dynamic', 'fast_cut', 'creative_reveal', 'white_doodle', 'minimal', 'ugc_review', 'nature_fresh', 'playful_viral'},
    'gadget': {'tech_demo', 'unboxing', 'cinematic', 'minimal', 'fast_cut', 'creative_reveal', 'ugc_review', 'flatlay', 'luxury', 'studio_360_safe', 'dynamic'},
    'home': {'cozy_home', 'flatlay', 'lifestyle', 'creative_reveal', 'cinematic', 'minimal', 'fast_cut', 'pov_demo', 'unboxing', 'white_doodle', 'ugc_review'},
    'accessory': {'luxury', 'beauty_macro', 'flatlay', 'cinematic', 'studio_360_safe', 'fashion_editorial', 'golden_hour', 'white_doodle', 'minimal', 'unboxing'},
    'other': {'cinematic', 'minimal', 'dynamic', 'luxury', 'lifestyle', 'ugc_review', 'flatlay', 'unboxing', 'creative_reveal', 'studio_360_safe', 'white_doodle', 'fast_cut', 'playful_viral'},
}

def prompt_style_menu(product_type='other'):
    available = storyboard_styles()
    allowed = PRODUCT_STYLE_KEYS.get(product_type, PRODUCT_STYLE_KEYS['other'])
    matching = [(key, label) for key, label in available if key in allowed]
    # If catalog entries are customized, never leave the user with an empty style menu.
    if not matching:
        matching = available
    rows = [[InlineKeyboardButton('🎲 Auto (Disyorkan)', callback_data='prompt_style:auto')]]
    rows.extend([[InlineKeyboardButton(label, callback_data='prompt_style:' + key)]
                 for key, label in matching])
    rows.append([InlineKeyboardButton('↩️ Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def prompt_idea_choice_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎬 Tambah idea video siap (pilihan)', callback_data='prompt_idea:yes')],
        [InlineKeyboardButton('➡️ Teruskan tanpa idea tambahan', callback_data='prompt_idea:skip')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_category_menu():
    rows = []
    categories = PROMPT_LIBRARY.get('categories', [])
    for index in range(0, len(categories), 2):
        pair = categories[index:index + 2]
        rows.append([InlineKeyboardButton(f"{item.get('emoji', '🎬')} {item['label']}", callback_data=f"pcat:{item['id']}") for item in pair])
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
    rows.append([InlineKeyboardButton('🏠 Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def inject_product_details(prompt_text: str, details: str) -> str:
    details = ' '.join((details or '').split()).strip()
    if not details:
        return prompt_text
    note = ('PRODUCT NAME / DETAILS FROM USER: ' + details +
            '. Use these details only as supporting context. The uploaded image remains the sole visual source of truth; never invent or alter product features.\n\n')
    first_sentence_end = prompt_text.find('. ')
    if first_sentence_end >= 0:
        return prompt_text[:first_sentence_end + 2] + note + prompt_text[first_sentence_end + 2:]
    return note + prompt_text


def video_input_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📷 Upload Gambar', callback_data='video_input:photos')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


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


def background_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📷 Kekalkan Asal', callback_data='background:original')],
        [InlineKeyboardButton('⬜ Studio Putih', callback_data='background:white'),
         InlineKeyboardButton('🟤 Studio Beige', callback_data='background:beige')],
        [InlineKeyboardButton('⬛ Luxury Gelap', callback_data='background:dark'),
         InlineKeyboardButton('🌸 Pastel', callback_data='background:pastel')],
        [InlineKeyboardButton('✨ Gradient Krim', callback_data='background:gradient'),
         InlineKeyboardButton('◯ Corak Halus', callback_data='background:pattern')],
        [InlineKeyboardButton('◐ Dua Tona', callback_data='background:duotone'),
         InlineKeyboardButton('🌫️ Kelabu Lembut', callback_data='background:mist')],
        [InlineKeyboardButton('↩️ Semak Gambar', callback_data='photos_order')],
    ])


def duration_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⏱️ 10 saat', callback_data='duration:10'),
         InlineKeyboardButton('⏱️ 15 saat', callback_data='duration:15')],
        [InlineKeyboardButton('⏱️ 20 saat', callback_data='duration:20')],
        [InlineKeyboardButton('↩️ Semak Gambar', callback_data='photos_order')],
    ])


def prompt_scene_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✨ Auto (Disyorkan)', callback_data='scene:auto')],
        [InlineKeyboardButton('📸 Studio Premium', callback_data='scene:studio'), InlineKeyboardButton('🌑 Mewah Gelap', callback_data='scene:dark')],
        [InlineKeyboardButton('🏡 Ruang Rumah', callback_data='scene:home'), InlineKeyboardButton('🌿 Alam Semula Jadi', callback_data='scene:nature')],
        [InlineKeyboardButton('☀️ Cerah Minimalis', callback_data='scene:minimal')]
    ])


def home_keyboard():
    return ReplyKeyboardMarkup([['🏠 Menu Utama']], resize_keyboard=True, is_persistent=True)


def is_admin(user_id):
    return str(user_id) in [x.strip() for x in os.environ.get('ADMIN_USER_IDS', '37141287').split(',')]


async def progress_update(message, percent, detail):
    """Milestone-based progress, not an invented time or FFmpeg frame estimate."""
    try:
        await message.edit_text(f"⏳ DALAM PROSES — {percent}%\n{detail}")
    except Exception:
        logging.debug('Progress message edit unavailable', exc_info=True)


def prompt_wait_animation():
    """Build a lightweight animated waiting GIF locally, without an external API."""
    frames = []
    for step in range(12):
        im = Image.new('RGB', (360, 160), (19, 24, 39))
        draw = ImageDraw.Draw(im)
        draw.rounded_rectangle((20, 20, 340, 140), radius=18, outline=(66, 78, 106), width=2)
        draw.text((42, 43), 'KLIPPO', fill=(245, 246, 250))
        draw.text((42, 68), 'MENYEDIAKAN PROMPT...', fill=(192, 204, 226))
        for dot in range(6):
            x = 53 + dot * 49
            active = dot == (step // 2) % 6
            draw.ellipse((x, 105, x + 13, 118), fill=(89, 214, 175) if active else (73, 86, 111))
        frames.append(im)
    output = BytesIO()
    frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:],
                   duration=130, loop=0, optimize=True)
    output.seek(0)
    output.name = 'klippo_menunggu.gif'
    return output


FAQ_ITEMS = (
    ('Cara jana video', 'Upload 1-5 gambar, tekan Selesai, masukkan tajuk penuh produk Shopee, kemudian pilih latar, tempoh, gerakan dan muzik.', ('GAMBAR PRODUK', 'TAJUK PRODUK', 'PILIH GAYA', 'JANA VIDEO')),
    ('Perlu pautan Shopee?', 'Tidak. Masukkan tajuk penuh produk, bukan URL atau pautan Shopee.', ('GAMBAR PRODUK', 'TAJUK PENUH', 'BUKAN PAUTAN')),
    ('Tempoh video', 'Pilih 10, 15 atau 20 saat. Masa menunggu bergantung pada gambar dan kesibukan pelayan.', ('10 SAAT', '15 SAAT', '20 SAAT')),
    ('Latar gambar', 'Anda boleh kekalkan latar asal atau pilih latar lain. Gambar berlatar kompleks mungkin tidak dapat diasingkan dengan sempurna.', ('LATAR ASAL', 'LATAR STUDIO', 'SEMAK HASIL')),
    ('Fungsi Prompt', 'Prompt menyediakan arahan teks untuk penjana video AI lain. Ia bukan fail video yang telah siap.', ('PILIH PROMPT', 'ISI MAKLUMAT', 'SALIN TEKS')),
    ('Video gagal dijana', 'Cuba gambar yang lebih jelas, kurangkan bilangan gambar dan jana semula. Simpan mesej ralat jika masalah berulang.', ('SEMAK GAMBAR', 'CUBA SEMULA', 'SIMPAN RALAT')),
    ('Adakah video generatif?', 'Tidak. KLIPPO menyunting gambar asal dengan animasi 2D, transisi dan muzik; ia tidak mencipta rakaman produk baharu.', ('GAMBAR ASAL', 'EFEK 2D', 'VIDEO MP4')),
)


def faq_menu():
    rows = [[InlineKeyboardButton(f'{i+1}. {item[0]}', callback_data=f'faq:{i}')] for i, item in enumerate(FAQ_ITEMS)]
    rows.append([InlineKeyboardButton('🏠 Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def faq_example(index):
    """Create a lightweight, original illustrated flow for each FAQ; no external assets."""
    from PIL import Image, ImageDraw, ImageFont
    title, _, steps = FAQ_ITEMS[index]
    w, h = 720, 540
    im = Image.new('RGB', (w, h), (245, 247, 252))
    d = ImageDraw.Draw(im)
    fonts = ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
             '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf')
    font_path = next((p for p in fonts if Path(p).is_file()), None)
    def font(size):
        return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
    d.rounded_rectangle((24, 24, 696, 516), radius=28, fill=(255, 255, 255), outline=(218, 225, 236), width=2)
    d.text((54, 50), 'KLIPPO  /  FAQ', font=font(22), fill=(69, 87, 115))
    d.text((54, 98), title, font=font(32), fill=(27, 38, 58))
    d.line((54, 155, 666, 155), fill=(225, 230, 240), width=2)
    count = len(steps)
    box_w = min(550, (612 - (count - 1) * 12) // count)
    start_x = (w - (count * box_w + (count - 1) * 12)) // 2
    for i, label in enumerate(steps):
        x = start_x + i * (box_w + 12)
        d.rounded_rectangle((x, 218, x + box_w, 352), radius=17, fill=(235, 242, 253), outline=(170, 194, 229), width=2)
        d.ellipse((x + box_w//2 - 20, 234, x + box_w//2 + 20, 274), fill=(55, 103, 181))
        num = str(i + 1)
        bb = d.textbbox((0, 0), num, font=font(23))
        d.text((x + box_w//2 - (bb[2]-bb[0])//2, 239), num, font=font(23), fill='white')
        label_font = font(15 if box_w < 145 else 18)
        bb = d.textbbox((0, 0), label, font=label_font)
        d.text((x + box_w//2 - (bb[2]-bb[0])//2, 296), label, font=label_font, fill=(30, 49, 80))
    d.text((54, 432), 'Contoh ilustrasi aliran penggunaan', font=font(19), fill=(99, 113, 136))
    output = BytesIO()
    im.save(output, format='PNG')
    output.seek(0)
    output.name = f'klippo_faq_{index+1}.png'
    return output


def main_menu(user_id=None):
    rows = [
        [InlineKeyboardButton('🎬 Jana Video Transisi', callback_data='make'), InlineKeyboardButton('✍️ Prompt', callback_data='prompt')],
        [InlineKeyboardButton('🎞️ Gabung Video', callback_data='merge')],
        [InlineKeyboardButton('🔄 Tukar Format Video', callback_data='convert')],
        [InlineKeyboardButton('💎 Langganan', callback_data='subscription'), InlineKeyboardButton('👤 Akaun Saya', callback_data='account')],
        [InlineKeyboardButton('❓ FAQ', callback_data='help')],
    ]
    if user_id is not None and is_admin(user_id):
        rows.append([InlineKeyboardButton('🛡️ Panel Admin', callback_data='admin')])
    return InlineKeyboardMarkup(rows)


def style_menu():
    """Simple optional styles; retain all legacy render styles internally."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎬 Smooth (Disyorkan)', callback_data='style:smooth')],
        [InlineKeyboardButton('✨ Premium', callback_data='style:cinematic')],
        [InlineKeyboardButton('⚡ Dynamic', callback_data='style:dynamic')],
        [InlineKeyboardButton('↩️ Pilih Muzik', callback_data='music')],
    ])


def motion_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton(label,callback_data='motion:'+key)] for key,label in [('auto','✨ Auto Creative (Disyorkan)'),('stop','🎞️ Stop Motion Pop'),('spin','🌀 Spin-In'),('smooth','🎬 Smooth Motion'),('hand','🖐️ Cute Hand Place & Exit'),('hero','💎 Hero Close-up'),('minimal','🤍 Minimal Studio')]])


def music_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Auto Beat', callback_data='music:auto')],
        [InlineKeyboardButton('📎 Upload Muzik Sendiri', callback_data='music:custom')],
        [InlineKeyboardButton('↩️ Tukar Gaya', callback_data='styles')],
    ])


def confirm_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Hasilkan Video', callback_data='confirm')],
        [InlineKeyboardButton('✨ Tukar Efek', callback_data='effects')],
        [InlineKeyboardButton('🎞️ Tukar Pergerakan', callback_data='motions'), InlineKeyboardButton('🎵 Tukar Muzik', callback_data='music')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def make_promo_beat(variant=0) -> Path | None:
    """Generate an original upbeat instrumental loop, with no external music licensing."""
    import math
    import wave
    from array import array
    import random
    bpm = (124, 116, 128, 120, 132)[variant % 5]
    target = Path(tempfile.gettempdir()) / f'klippo_promo_beat_{bpm}_v2.wav'
    if target.is_file() and target.stat().st_size > 50000:
        return target
    rate, seconds = 22050, 24
    beat = 60 / bpm
    rng = random.Random(124 + variant)
    samples = array('h')
    for n in range(rate * seconds):
        t = n / rate
        phase = t % beat
        half = t % (beat / 2)
        kick_env = math.exp(-phase * 23)
        kick = math.sin(2 * math.pi * (54 * phase + 55 * phase * phase)) * kick_env * .55
        snare_phase = (t - beat) % (2 * beat)
        snare = (rng.random() * 2 - 1) * math.exp(-snare_phase * 31) * .16
        hat = (rng.random() * 2 - 1) * math.exp(-half * 110) * .075
        # Bright major pentatonic synth pluck, deliberately short and rhythmic.
        notes = ((220.0,277.18,329.63,440.0,329.63,277.18,246.94,329.63),
                 (261.63,329.63,392.0,329.63,293.66,392.0,440.0,392.0),
                 (196.0,246.94,293.66,392.0,293.66,246.94,220.0,293.66),
                 (246.94,311.13,369.99,493.88,369.99,311.13,277.18,369.99),
                 (220.0,329.63,440.0,329.63,277.18,329.63,246.94,277.18))[variant % 5]
        step = int(t / (beat / 2)) % len(notes)
        p = t % (beat / 2)
        freq = notes[step]
        pluck = (math.sin(2*math.pi*freq*p) + .28*math.sin(2*math.pi*freq*2*p)) * math.exp(-p*9) * .12
        bass_note = (110.0, 138.59, 164.81, 123.47)[int(t/(beat*4))%4]
        bass = math.sin(2*math.pi*bass_note*phase) * math.exp(-phase*4) * .16
        amp = max(-.92, min(.92, kick + snare + hat + pluck + bass))
        samples.append(int(amp * 32767))
    with wave.open(str(target), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    return target


def resolve_music(choice: str, style: str) -> Path | None:
    if choice == 'none' or choice == 'custom':
        return None
    if choice == 'auto':
        import random
        return make_promo_beat(random.SystemRandom().randrange(5))
    name = choice
    path = MUSIC_DIR / (name + '.mp3')
    return path if path.is_file() else None


def verified_video_hook(info: str) -> str | None:
    """Conservative, local text-only hook. Never send product photos to a hook AI."""
    info = ' '.join((info or '').split())[:100]
    if not info or not re.fullmatch(r"[\\w\\s.,&+()/-]+", info, flags=re.UNICODE):
        return None
    if len(info) > 48:
        info = info[:48].rsplit(' ', 1)[0]
    return 'KENALI ' + info.upper() if info else None


def hook_card(still: Path, hook: str) -> None:
    """Place a readable factual headline in the top safe area of the first shot."""
    with Image.open(still) as source:
        image = source.convert('RGB')
    draw = ImageDraw.Draw(image, 'RGBA')
    w, h = image.size
    font_path = next((p for p in (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'
    ) if Path(p).is_file()), None)
    font = ImageFont.truetype(font_path, max(20, round(w * .046))) if font_path else ImageFont.load_default()
    max_width = round(w * .85)
    while draw.textbbox((0, 0), hook, font=font)[2] > max_width and getattr(font, 'size', 12) > 19:
        font = ImageFont.truetype(font_path, font.size - 2)
    top = round(h * .095)
    text_box = draw.textbbox((0, 0), hook, font=font)
    text_w = text_box[2] - text_box[0]
    text_h = text_box[3] - text_box[1]
    x = (w - text_w) // 2
    draw.rounded_rectangle((x-22, top-14, x+text_w+22, top+text_h+22),
                           radius=18, fill=(14, 20, 29, 195))
    draw.text((x, top-text_box[1]), hook, font=font, fill=(255, 255, 255, 255))
    image.save(still, quality=96, subsampling=0)


def smart_frame(img, motion):
    """Conservative crop for plain backgrounds, otherwise preserve the entire photo."""
    target = (round(WIDTH * 1.22), round(HEIGHT * 1.22))
    thumb = img.resize((80, 80), Image.Resampling.BILINEAR)
    corners = [thumb.getpixel(p) for p in ((0, 0), (79, 0), (0, 79), (79, 79))]
    bg = tuple(sum(c[k] for c in corners) // 4 for k in range(3))
    spread = max(max(c[k] for c in corners) - min(c[k] for c in corners) for k in range(3))
    if spread < 24:
        mask = Image.new('L', (80, 80))
        pixels = mask.load()
        for y in range(80):
            for x in range(80):
                rgb = thumb.getpixel((x, y))
                pixels[x, y] = 255 if max(abs(rgb[k] - bg[k]) for k in range(3)) > 45 else 0
        box = mask.getbbox()
        if box:
            l, t, r, b = box
            area = (r-l)*(b-t)/6400
            if .04 < area < .75 and l > 3 and t > 3 and r < 77 and b < 77:
                pad = .18 if motion in (0, 2) else .12
                dx, dy = (r-l)*pad, (b-t)*pad
                box = (max(0, int((l-dx)*img.width/80)),
                       max(0, int((t-dy)*img.height/80)),
                       min(img.width, int((r+dx)*img.width/80)),
                       min(img.height, int((b+dy)*img.height/80)))
                img = img.crop(box)
    fitted = ImageOps.contain(img, target, method=Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', target, bg if spread < 24 else (242, 242, 242))
    canvas.paste(fitted, ((target[0]-fitted.width)//2, (target[1]-fitted.height)//2))
    return canvas


def render_product_motion(layers, output, music, duration, on_progress=None, doodle='none'):
    """Product-only advertising: deliberate moves on musical phrases, clean beat cuts."""
    # Built-in promotional beats have known BPM. For custom music use evenly spaced
    # editorial cuts; do not claim to detect beats in arbitrary uploaded audio.
    import re
    tempo_match = re.search(r'klippo_promo_beat_([0-9]+)_v2', str(music)) if music else None
    bpm = int(tempo_match.group(1)) if tempo_match else None
    motion_variant = ((bpm or 124) // 4) % 3
    if bpm:
        phrase = 8 * 60 / bpm
        boundaries = [0, phrase, phrase * 2, duration] if duration >= phrase * 2 + 1 else [0, duration / 2, duration]
    else:
        count = 2 if duration <= 10 else 3
        boundaries = [duration * i / count for i in range(count + 1)]
    with tempfile.TemporaryDirectory(prefix='klippo_motion_') as td:
        tmp = Path(td)
        clips = []
        for i in range(len(boundaries)-1):
            cutout_path, choice = layers[i % len(layers)]
            with Image.open(cutout_path) as opened:
                fg = opened.convert('RGBA')
            bbox = fg.getchannel('A').getbbox()
            if not bbox:
                raise ValueError('Produk tidak dapat dikesan dalam imej lutsinar')
            fg = fg.crop(bbox)
            # Gentle detail enhancement preserves the product's original colors.
            from PIL import ImageEnhance
            alpha = fg.getchannel('A')
            rgb = Image.merge('RGB', fg.split()[:3])
            rgb = ImageEnhance.Contrast(rgb).enhance(1.055)
            rgb = ImageEnhance.Sharpness(rgb).enhance(1.12)
            fg = rgb.convert('RGBA')
            fg.putalpha(alpha)
            # Soft contact shadow follows the product instead of remaining on the backdrop.
            pad = max(12, round(max(fg.size) * .07))
            shadow_alpha = Image.new('L', (fg.width + 2*pad, fg.height + 2*pad), 0)
            shadow_alpha.paste(alpha, (pad, pad + pad//3))
            shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(max(5, pad//2)))
            shadow_alpha = shadow_alpha.point(lambda v: round(v * .24))
            shadow = Image.new('RGBA', shadow_alpha.size, (0, 0, 0, 0))
            shadow.putalpha(shadow_alpha)
            shadow.alpha_composite(fg, (pad, pad))
            fg = shadow
            # Clearly distinct framing, not tiny jitter. Never fabricate another view.
            scale = ((.63, .76, .70), (.70, .64, .77), (.67, .78, .69))[motion_variant][i % 3]
            fg.thumbnail((int(WIDTH * scale), int(HEIGHT * .66)), Image.Resampling.LANCZOS)
            fg_path = tmp / f'product_{i}.png'
            fg.save(fg_path)
            bg = (_scene_background((WIDTH, HEIGHT), choice) if choice not in BACKGROUNDS
                  else Image.new('RGBA', (WIDTH, HEIGHT), BACKGROUNDS[choice] + (255,)))
            bg_path = tmp / f'background_{i}.png'
            bg.convert('RGB').save(bg_path)
            frames = max(1, round((boundaries[i+1]-boundaries[i])*FPS))
            p = f'min(n/{max(frames-1,1)},1)'
            ease = f'({p}*{p}*(3-2*{p}))'
            cx, cy = '(W-w)/2', '(H-h)/2'
            if i % 3 == 0:  # confident entrance on the first musical phrase
                direction = -1 if motion_variant == 1 else 1
                x, y = f'{cx}+W*{direction * .22}*(1-{ease})', f'{cy}+H*.035*(1-{ease})'
            elif i % 3 == 1:  # closer product detail, gentle lift
                x, y = f'{cx}-W*.035*{ease}', f'{cy}+H*.045*(1-{ease})'
            else:  # stable hero finish
                x, y = cx, f'{cy}+H*.025*(1-{ease})'
            clip = tmp / f'shot_{i}.mp4'
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1',
                   '-loop','1','-framerate',str(FPS),'-i',str(bg_path),
                   '-loop','1','-framerate',str(FPS),'-i',str(fg_path),
                   '-filter_complex',f"[0:v]format=rgba[bg];[1:v]format=rgba[fg];[bg][fg]overlay=x='{x}':y='{y}':eval=frame:shortest=1,format=yuv420p[v]",
                   '-map','[v]','-frames:v',str(frames),'-an','-c:v','libx264',
                   '-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(clip)]
            subprocess.run(cmd, check=True, timeout=120, capture_output=True, text=True)
            clips.append(clip)
            if on_progress:
                on_progress(45+round(30*(i+1)/(len(boundaries)-1)), f'Gerakan ikut frasa muzik {i+1}/{len(boundaries)-1}...')
        joined = tmp / 'joined.mp4'
        cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y']
        for clip in clips:
            cmd += ['-i',str(clip)]
        chain = ''.join(f'[{i}:v]' for i in range(len(clips)))+f'concat=n={len(clips)}:v=1:a=0,format=yuv420p[v]'
        cmd += ['-filter_complex',chain,'-map','[v]','-an','-c:v','libx264',
                '-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(joined)]
        subprocess.run(cmd, check=True, timeout=150, capture_output=True, text=True)
        if doodle != 'none':
            decorated = tmp / 'decorated.mp4'
            apply_overlay(joined, decorated, doodle, WIDTH, HEIGHT, duration, background=layers[0][1])
            joined = decorated
        if music:
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(joined),
                   '-stream_loop','-1','-i',str(music),'-map','0:v:0','-map','1:a:0',
                   '-af',f'afade=t=out:st={max(0,duration-0.35):.3f}:d=0.35',
                   '-t',str(duration),'-c:v','copy','-c:a','aac','-b:a','128k',
                   '-movflags','+faststart',str(output)]
        else:
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(joined),
                   '-t',str(duration),'-c','copy','-movflags','+faststart',str(output)]
        subprocess.run(cmd, check=True, timeout=180, capture_output=True, text=True)


def _hand_place_asset(width, variant, direction):
    """Simple transparent flat hand PNG-like layer, translated as a whole."""
    w = max(120, int(width))
    h = round(w * .46)
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    skins = ((238,185,146,255),(182,125,91,255),(244,207,177,255),(139,91,68,255),(214,155,119,255))
    sleeves = ((235,151,173,255),(134,178,210,255),(187,167,215,255),(139,185,157,255),(234,195,126,255))
    skin = skins[variant % len(skins)]
    sleeve = sleeves[(variant // 2) % len(sleeves)]
    draw.rounded_rectangle((0,int(h*.23),int(w*.57),int(h*.78)),radius=int(h*.13),fill=sleeve)
    draw.rounded_rectangle((int(w*.43),int(h*.29),int(w*.80),int(h*.73)),radius=int(h*.17),fill=skin)
    for a,b in ((.27,.39),(.42,.54),(.56,.68)):
        draw.rounded_rectangle((int(w*.66),int(h*a),int(w*.96),int(h*b)),radius=max(2,int(h*.045)),fill=skin)
    if variant % 3 == 1:
        draw.line((int(w*.15),int(h*.25),int(w*.15),int(h*.75)),fill=(255,255,255,170),width=3)
    if direction[0] > 0:
        im = ImageOps.mirror(im)
    if direction[0] == 0:
        im = im.rotate(-90 if direction[1] < 0 else 90,expand=True)
    elif direction[1]:
        im = im.rotate((-30 if direction[1] < 0 else 30) * (1 if direction[0] < 0 else -1),expand=True)
    return im


def _premium_studio_background(size, choice):
    """CPU-friendly studio light and floor; computed once per render, not per frame."""
    import math
    w, h = size
    palettes = {
        'white': ((252, 251, 248), (226, 224, 220)),
        'beige': ((250, 241, 225), (202, 179, 153)),
        'dark': ((65, 65, 73), (20, 21, 27)),
        'pastel': ((252, 238, 244), (218, 194, 209)),
        'gradient': ((253, 247, 236), (215, 195, 170)),
        'pattern': ((251, 248, 241), (222, 213, 199)),
        'duotone': ((247, 237, 222), (199, 180, 161)),
        'mist': ((249, 250, 250), (203, 212, 219)),
    }
    top, bottom = palettes.get(choice, palettes['gradient'])
    canvas = Image.new('RGBA', size)
    draw = ImageDraw.Draw(canvas)
    for y in range(h):
        t = y / max(1, h-1)
        t = t*t*(3-2*t)
        # Wide overhead softbox: brightest behind the product, darker at the edges.
        for x0 in range(0, w, 12):
            x1 = min(w-1, x0+11)
            dx = (x0 + 5.5 - w*.50) / max(1, w*.72)
            dy = (y-h*.37) / max(1, h*.76)
            light = max(0.0, 1.0-dx*dx-dy*dy)*.105
            edge = min(1.0, dx*dx*.12 + ((y/h)-.42)**2*.055)
            color = tuple(max(0,min(255,round(top[k]*(1-t)+bottom[k]*t + 255*light - 255*edge))) for k in range(3))
            draw.rectangle((x0,y,x1,y), fill=color+(255,))
    # Elliptical floor reflection anchors the product instead of a flat color card.
    floor = Image.new('RGBA', size, (0,0,0,0))
    fd = ImageDraw.Draw(floor)
    cx, cy = w//2, round(h*.765)
    for i in range(15, 0, -1):
        rx = round(w*(.34 + i*.009))
        ry = round(h*(.018 + i*.002))
        a = round((16-i)*.38)
        fd.ellipse((cx-rx,cy-ry,cx+rx,cy+ry), fill=(0,0,0,a))
    floor = floor.filter(ImageFilter.GaussianBlur(max(3,w//45)))
    return Image.alpha_composite(canvas, floor)


def render_creative_motion(layers, output, music, duration, on_progress=None, doodle='none', mode='auto', product_info=''):
    """Deliberate held-pose stop motion; source cutout only, no invented 3D views."""
    import math
    from PIL import ImageEnhance
    with tempfile.TemporaryDirectory(prefix='klippo_creative_') as td:
        tmp = Path(td)
        frames_dir = tmp / 'frames'
        frames_dir.mkdir()
        total = max(1, round(duration * FPS))
        import hashlib
        variant_hash = hashlib.sha256()
        for product_path, background_choice in layers:
            with open(product_path, 'rb') as product_file:
                for chunk in iter(lambda: product_file.read(65536), b''):
                    variant_hash.update(chunk)
            variant_hash.update(background_choice.encode('utf-8'))
        variant_hash.update(str(duration).encode('ascii'))
        variant = int(variant_hash.hexdigest()[:4], 16) % 4
        # Distinct, deterministic entrance per product; never shake the hero shot.
        entrances = ((-.72, 0, -12), (.72, 0, 12), (0, -.58, -9),
                     (0, .58, 9), (-.56, -.38, -10), (.56, -.38, 10),
                     (-.56, .38, -8), (.56, .38, 8))
        entrance = entrances[int(variant_hash.hexdigest()[4:8], 16) % len(entrances)]
        hand_place = mode == 'hand'
        if hand_place:
            import secrets
            entrance = entrances[secrets.randbelow(len(entrances))]
            hand_variant = secrets.randbelow(15)
            entrance = (entrance[0], entrance[1], 0)
        if mode == 'minimal':
            entrance = (0, .12, 0)
        elif mode == 'hero':
            entrance = (0, .22, 0)
        elif mode == 'smooth':
            entrance = (entrance[0]*.35, entrance[1]*.35, entrance[2]*.25)
        elif mode == 'spin':
            entrance = (entrance[0]*.42, entrance[1]*.42, 28 if entrance[2] >= 0 else -28)
        entrance_seconds = min(1.65, max(.9, duration * .12))
        hold = 1
        sources = []
        for cutout_path, choice in layers:
            with Image.open(cutout_path) as opened:
                fg = opened.convert('RGBA')
            bbox = fg.getchannel('A').getbbox()
            if not bbox:
                raise ValueError('Produk tidak dapat diasingkan')
            fg = fg.crop(bbox)
            alpha = fg.getchannel('A')
            rgb = ImageEnhance.Contrast(fg.convert('RGB')).enhance(1.045)
            fg = rgb.convert('RGBA')
            fg.putalpha(alpha)
            # Fill the hero area proportionally without cropping the real product.
            # Leave the upper and lower safe zones available for handwritten captions.
            fg.thumbnail((round(WIDTH*.76),round(HEIGHT*.53)),Image.Resampling.LANCZOS)
            sources.append((fg,choice))
        studio_backgrounds = {choice: _premium_studio_background((WIDTH, HEIGHT), choice) for _, choice in layers}
        # A subtle ground shadow is pre-rendered once per product size, not blurred every frame.
        shadow_cache = {}
        hand_image = _hand_place_asset(WIDTH*.37, hand_variant, entrance) if hand_place else None
        previous_frame = None
        previous_shot = -1
        transition_from = None
        for n in range(0,total,hold):
            t = n / FPS
            phase = t / max(duration, .01)
            shot = min(len(sources)-1, int(phase*len(sources)))
            fg, choice = sources[shot]
            shot_start = duration * shot / len(sources)
            shot_length = duration / len(sources)
            shot_t = max(0.0, t-shot_start)
            # Alternate restrained entrance direction between photos; keep hero and minimal centred.
            shot_entrance_vector = entrance
            if shot and mode not in ('hero', 'minimal', 'hand'):
                direction = -1 if shot % 2 else 1
                shot_entrance_vector = (entrance[0]*direction, entrance[1]*direction,
                                        entrance[2]*direction)
            # Reset the restrained reveal per shot, not just at video start.
            shot_entrance = min(entrance_seconds, max(.28, shot_length*.36))
            u = min(1.0, shot_t / shot_entrance)
            ease = 1 - (1-u)**3
            if u < 1:
                angle = shot_entrance_vector[2] * (1-ease)
                scale = (.96 + .04*ease) if mode == 'minimal' else ((.79 + .21*ease) if mode == 'hero' else (.88 + .12*ease))
                dx = round(WIDTH * shot_entrance_vector[0] * (1-ease))
                dy = round(HEIGHT * shot_entrance_vector[1] * (1-ease))
            else:
                angle = 0
                # Gentle editorial push-in after the entrance; no constant wobble.
                hero_u = min(1.0, max(0.0, (shot_t-shot_entrance)/max(.25,shot_length-shot_entrance)))
                hero_ease = hero_u*hero_u*(3-2*hero_u)
                push = .11 if mode == 'hero' else (.008 if mode == 'minimal' else (.022 if mode == 'stop' else .035))
                scale = 1.0 + push*hero_ease
                dx = dy = 0
            if mode == 'stop':
                # Intentional held poses, rather than a continuous camera move.
                scale = round(scale * 12) / 12
            size = (max(1,round(fg.width*scale)),max(1,round(fg.height*scale)))
            transformed = fg.resize(size,Image.Resampling.LANCZOS).rotate(angle,Image.Resampling.BICUBIC,expand=True)
            alpha = transformed.getchannel('A')
            shadow_key = (shot, transformed.size, round(angle, 1))
            shadow = shadow_cache.get(shadow_key)
            if shadow is None:
                shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(max(5,round(WIDTH*.022))))
                shadow_alpha = shadow_alpha.point(lambda a: round(a*.16))
                shadow = Image.new('RGBA',transformed.size,(0,0,0,0))
                shadow.putalpha(shadow_alpha)
                # Bound memory use on long videos with many unique camera positions.
                if len(shadow_cache) >= 24:
                    shadow_cache.clear()
                shadow_cache[shadow_key] = shadow
            canvas = studio_backgrounds[choice].copy()
            x = round((WIDTH-transformed.width)/2)+dx
            y = round((HEIGHT-transformed.height)/2)+dy
            # Clip overlays safely when a pose extends outside the canvas.
            # Composite directly onto the RGB canvas. Full-canvas RGBA layers
            # multiplied peak RAM on small Render instances.
            canvas.paste(shadow, (x+round(WIDTH*.008), y+round(HEIGHT*.012)), shadow)
            canvas.paste(transformed, (x, y), transformed)
            if hand_place and shot_t < shot_entrance + .82:
                retreat = max(0.0, min(1.0, (shot_t-shot_entrance-.10)/.65))
                retreat = retreat*retreat*(3-2*retreat)
                hx = round((WIDTH-hand_image.width)/2 + WIDTH*entrance[0]*((1-ease)+retreat))
                hy = round((HEIGHT-hand_image.height)/2 + HEIGHT*entrance[1]*((1-ease)+retreat))
                canvas.paste(hand_image, (hx, hy), hand_image)
                canvas.paste(transformed, (x, y), transformed)
            frame = canvas.convert('RGB')
            if shot != previous_shot:
                transition_from = previous_frame.copy() if previous_shot >= 0 and previous_frame is not None else None
                previous_shot = shot
            # Cross-dissolve from the preceding shot, avoiding a hard cut.
            if transition_from is not None:
                fade_seconds = min(.32, shot_length*.16)
                mix = min(1.0, shot_t / max(.01, fade_seconds))
                mix = mix*mix*(3-2*mix)
                if mix < 1.0:
                    frame = Image.blend(transition_from, frame, mix)
                else:
                    transition_from = None
            previous_frame = frame
            for k in range(n,min(total,n+hold)):
                frame.save(frames_dir / f'{k:05d}.png',compress_level=1)
            if on_progress and (n == 0 or n % max(hold,round(FPS*2/hold)*hold) == 0):
                on_progress(45+round(30*n/total),'Membina video produk dan transisi...')
        joined = tmp / 'creative.mp4'
        if on_progress:
            on_progress(76, 'Frame siap. Menyusun video HD...')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1','-filter_threads','1',
                        '-framerate',str(FPS),'-i',str(frames_dir/'%05d.png'),'-c:v','libx264','-threads','1',
                        '-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(joined)],check=True,timeout=240,capture_output=True,text=True)
        if on_progress:
            on_progress(79, 'Video asas siap. Mengemas kini efek...')
        if doodle != 'none':
            decorated = tmp / 'decorated.mp4'
            if on_progress:
                on_progress(81, 'Menambah efek visual...')
            apply_overlay(joined,decorated,doodle,WIDTH,HEIGHT,duration,background=layers[0][1],seed=variant_hash.hexdigest())
            joined = decorated
        # Three staggered handwriting reveals after the product settles / hand exits.
        if on_progress:
            on_progress(83, 'Menyediakan tulisan promosi...')
        labels = make_handwriting_labels(tmp, WIDTH, HEIGHT, background=layers[0][1],
                                         seed=variant_hash.hexdigest(), product_info=product_info)
        labelled = tmp / 'labelled.mp4'
        label_cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(joined)]
        for label_path in labels:
            label_cmd += ['-framerate',str(FPS),'-loop','1','-i',str(label_path)]
        reveal_start = entrance_seconds + (1.0 if hand_place else .25)
        graph = []
        prev = '0:v'
        for i in range(3):
            start = min(max(0, duration-1.1), reveal_start+i*.72)
            end = max(start+.2, duration-.12)
            graph.append(f'[{i+1}:v]format=rgba,fade=t=in:st={start:.2f}:d=0.48:alpha=1[ink{i}]')
            graph.append(f'[{prev}][ink{i}]overlay=0:0:shortest=1:enable=\'between(t,{start:.2f},{end:.2f})\'[v{i}]')
            prev = f'v{i}'
        # One final grade and a short cinematic exit, without another encoding pass.
        graph.append(f'[{prev}]eq=contrast=1.025:saturation=1.045,fade=t=out:st={max(0,duration-.28):.2f}:d=0.28,format=yuv420p[final]')
        label_cmd += ['-filter_complex',';'.join(graph),
                      '-map','[final]','-an','-t',str(duration),'-c:v','libx264',
                      '-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(labelled)]
        subprocess.run(label_cmd,check=True,timeout=240,capture_output=True,text=True)
        if on_progress:
            on_progress(88, 'Kemasan video selesai. Menyediakan fail akhir...')
        joined = labelled
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(joined)]
        if music:
            cmd += ['-stream_loop','-1','-i',str(music),'-map','0:v:0','-map','1:a:0',
                    '-af',f'afade=t=in:st=0:d=.18,afade=t=out:st={max(0,duration-0.35):.3f}:d=0.35',
                    '-c:a','aac','-b:a','128k']
        else:
            cmd += ['-map','0:v:0']
        cmd += ['-t',str(duration),'-c:v','copy','-movflags','+faststart',str(output)]
        subprocess.run(cmd,check=True,timeout=180,capture_output=True,text=True)


def render_video(images: list[Path], output: Path, music: Path | None = None, style: str = 'hybrid', duration: int = DURATION, doodle: str = 'none', hook: str | None = None, on_progress=None, product_layers=None, motion='auto', product_info=''):
    """Produce CPU-friendly Ken Burns transitions. Morph is an approximation, not generative AI."""
    if product_layers:
        if motion in ('auto','stop','spin','smooth','hand','hero','minimal'):
            return render_creative_motion(product_layers, output, music, duration, on_progress, doodle, motion, product_info)
        return render_product_motion(product_layers, output, music, duration, on_progress, doodle)
    if style not in STYLES:
        raise ValueError("Unknown style")
    if not images:
        raise ValueError('No images')
    # Build a short multi-shot sequence even when the user supplies only 1–2 photos.
    # Reuse the original pixels; no fabricated alternate product views.
    source_count = len(images)
    if source_count == 1:
        shots = [(images[0], 0), (images[0], 5), (images[0], 2), (images[0], 7)]
    elif source_count == 2:
        shots = [(images[0], 0), (images[0], 4),
                 (images[1], 6), (images[1], 2)]
    else:
        shots = [(path, (i * 3 + i // 2) % 8) for i, path in enumerate(images)]
    n = len(shots)
    # Keep fades short enough for any image count and total duration.
    fade = min(0.42, duration / (n * 6.0)) if n > 1 else 0
    clip_duration = (duration + (n - 1) * fade) / n
    frames = max(1, round(clip_duration * FPS))
    with tempfile.TemporaryDirectory(prefix='render_') as td:
        temp = Path(td)
        clips = []
        for i, (path, motion) in enumerate(shots):
            logging.info('KLIPPO render shot %s/%s start', i + 1, n)
            with Image.open(path) as original:
                img = ImageOps.exif_transpose(original).convert('RGB')
                # Preserve framing: modest overscan gives zoompan room to move.
                img = smart_frame(img, motion)
                still = temp / f'still_{i}.jpg'
                img.save(still, quality=97, subsampling=0, optimize=True)
                # Product-only video: no generated text on any frame.
            clip = temp / f'clip_{i}.mp4'
            # Subtle editorial motion: vary direction, limit zoom change to 7.5%.
            # Expressions use the output-frame index 'on'; avoid abrupt jumps.
            t = f'min(on/{max(frames - 1, 1)},1)'
            progress = f'({t}*{t}*(3-2*{t}))'  # Smoothstep easing, gentle start and stop.
            # Distinct camera movements, not merely different xfade effects.
            # All movements use only the original visible product photograph.
            if motion == 0:  # slow push-in, centered
                motion_name = 'push-in'
                zoom = f'1.02+0.13*{progress}'
                x = '(iw-iw/zoom)/2'
                y = '(ih-ih/zoom)/2'
            elif motion == 1:  # left-to-right tracking
                motion_name = 'track-right'
                zoom = '1.17'
                x = f'(iw-iw/zoom)*(0.10+0.80*{progress})'
                y = '(ih-ih/zoom)/2'
            elif motion == 2:  # slow pull-out, centered
                motion_name = 'pull-out'
                zoom = f'1.16-0.13*{progress}'
                x = '(iw-iw/zoom)/2'
                y = '(ih-ih/zoom)/2'
            elif motion == 3:  # vertical reveal, bottom-to-top
                motion_name = 'rise'
                zoom = '1.17'
                x = '(iw-iw/zoom)/2'
                y = f'(ih-ih/zoom)*(0.90-0.80*{progress})'
            elif motion == 4:  # right-to-left tracking
                motion_name = 'track-left'
                zoom = '1.17'
                x = f'(iw-iw/zoom)*(0.90-0.80*{progress})'
                y = '(ih-ih/zoom)/2'
            elif motion == 5:  # restrained diagonal glide
                motion_name = 'diagonal-glide'
                zoom = f'1.12+0.04*{progress}'
                x = f'(iw-iw/zoom)*(0.18+0.64*{progress})'
                y = f'(ih-ih/zoom)*(0.20+0.60*{progress})'
            elif motion == 6:  # top-to-bottom editorial tilt
                motion_name = 'descend'
                zoom = '1.16'
                x = '(iw-iw/zoom)/2'
                y = f'(ih-ih/zoom)*(0.10+0.80*{progress})'
            else:  # reverse diagonal reveal
                motion_name = 'reverse-diagonal'
                zoom = f'1.16-0.035*{progress}'
                x = f'(iw-iw/zoom)*(0.80-0.60*{progress})'
                y = f'(ih-ih/zoom)*(0.80-0.60*{progress})'
            logging.info('KLIPPO shot %s movement: %s', i + 1, motion_name)
            vf = (f"zoompan=z='{zoom}':x='{x}':y='{y}':"
                  f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p")
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1','-filter_threads','1','-framerate','1','-i',str(still),
                   '-vf',vf,'-frames:v',str(frames),'-an','-c:v','libx264',
                   '-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(clip)]
            subprocess.run(cmd, check=True, timeout=100, capture_output=True, text=True)
            logging.info('KLIPPO render shot %s/%s complete (%s bytes)', i + 1, n, clip.stat().st_size)
            if on_progress:
                on_progress(40 + round(35 * (i + 1) / n), f'Merender babak {i + 1}/{n}...')
            clips.append(clip)
        if n == 1:
            video = clips[0]
        else:
            video = temp / 'joined.mp4'
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-filter_complex_threads','1']
            for clip in clips:
                cmd += ['-i',str(clip)]
            chains = []
            last = '[0:v]'
            for i in range(1,n):
                label = f'[v{i}]'
                offset = i * (clip_duration - fade)
                # Same-source cuts get a gentle dissolve; different photos use the selected style.
                same_photo = shots[i - 1][0] == shots[i][0]
                transition = 'fade' if same_photo else STYLES[style][(i - 1) % len(STYLES[style])]
                chains.append(f'{last}[{i}:v]xfade=transition={transition}:duration={fade:.4f}:offset={offset:.4f}{label}')
                last = label
            cmd += ['-filter_complex',';'.join(chains),'-map',last,'-an','-c:v','libx264',
                    '-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
            logging.info('KLIPPO joining %s rendered shots', n)
            if on_progress:
                on_progress(80, 'Menggabungkan babak video...')
            subprocess.run(cmd, check=True, timeout=150, capture_output=True, text=True)
            logging.info('KLIPPO shot joining complete (%s bytes)', video.stat().st_size)
        if doodle != 'none':
            decorated = temp / 'decorated.mp4'
            apply_overlay(video, decorated, doodle, WIDTH, HEIGHT, duration, background='original')
            video = decorated
        logging.info('KLIPPO finalizing video; music=%s', bool(music))
        if music:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),
                            '-stream_loop','-1','-i',str(music),'-map','0:v:0','-map','1:a:0',
                            '-af',f'afade=t=out:st={max(0,duration-0.35):.3f}:d=0.35',
                            '-t',str(duration),'-c:v','copy','-c:a','aac','-b:a','128k',
                            '-movflags','+faststart',str(output)],check=True,timeout=180)
        else:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),
                            '-t',str(duration),'-c','copy','-movflags','+faststart',str(output)],
                           check=True,timeout=180)

    logging.info('KLIPPO video output complete: %s bytes', output.stat().st_size)


def reset(context):
    context.user_data['photos'] = []
    context.user_data['music'] = None
    context.user_data['music_choice'] = 'auto'
    context.user_data['style'] = 'smooth'
    context.user_data['motion_choice'] = 'auto'
    context.user_data['duration'] = 10
    context.user_data['background'] = 'original'
    context.user_data['doodle_choice'] = 'auto'
    context.user_data['storyboard_mode'] = False
    context.user_data['prompt_mode'] = 'normal'
    context.user_data['video_product_info'] = ''
    context.user_data['product_description'] = ''
    context.user_data['shopee_url'] = ''
    context.user_data['prompt_vision'] = ''
    context.user_data['prompt_product'] = ''
    context.user_data['prompt_product_name'] = ''
    context.user_data['prompt_motion_choice'] = ''
    context.user_data['prompt_reference_photo'] = ''
    context.user_data['prompt_library_details'] = ''
    context.user_data['prompt_category'] = ''
    context.user_data['prompt_concept'] = ''
    context.user_data['stage'] = 'home'


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text('Akses tidak dibenarkan.')
        return
    if not klippo_db.configured():
        await update.effective_message.reply_text('🛡️ KLIPPO ADMIN\n\n⚠️ Sambungan Supabase belum ditetapkan di Render.')
        return
    try:
        pending = await asyncio.to_thread(klippo_db.pending_receipts)
        await update.effective_message.reply_text(
            f'🛡️ KLIPPO ADMIN\n\n🧾 Resit menunggu: {len(pending)} (10 terawal dipaparkan)\n💎 Kelulusan langganan: Manual',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧾 Semak Resit', callback_data='admin_pending')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    except Exception:
        logging.exception('Admin Supabase error')
        await update.effective_message.reply_text('⚠️ Gagal menghubungi database. Semak konfigurasi Supabase di Render.')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restore persistent Telegram keyboard and display inline menu."""
    if not context.user_data.get('busy'):
        reset(context)
    await update.effective_message.reply_text(
        '🏠 Butang Menu Utama tersedia di bawah ruang menaip.',
        reply_markup=home_keyboard()
    )
    await update.effective_message.reply_text(
        '🎬 KLIPPO | Studio Video Affiliate\n\n'
        'Pilih fungsi yang anda perlukan:\n\n'
        '🎬 Jana Video Transisi — gabungkan gambar pegun menjadi video MP4 menggunakan kesan transisi, zoom/pan 2D dan muzik. Ini transisi gambar sahaja; bukan video AI yang menghidupkan atau menggerakkan objek.\n'
        '✍️ Hasilkan Prompt — sediakan Prompt Biasa atau Prompt Storyboard terperinci untuk penjana video AI.\n'
        '🎞️ Gabung Video — cantum beberapa klip menjadi satu video.\n'
        '🔄 Tukar Format Video — sesuaikan video kepada format MP4 menegak untuk affiliate.\n'
        '💎 Langganan — lihat pelan dan cara pembayaran.\n'
        '👤 Akaun Saya — semak maklumat akaun dan status langganan.\n'
        '❓ Bantuan — panduan menggunakan KLIPPO.\n\n'
        '👇 Tekan pilihan di bawah untuk bermula:',
        reply_markup=main_menu(update.effective_user.id)
    )


async def account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not klippo_db.configured():
        await update.effective_message.reply_text(f'👤 AKAUN SAYA\n\nID Telegram: {user_id}\nStatus langganan belum dapat disemak.')
        return
    try:
        data = await asyncio.to_thread(klippo_db.subscription, user_id)
        status = 'Tiada langganan' if not data else f"{data['status']} (tamat: {data.get('expires_at') or '-'})"
        await update.effective_message.reply_text(f'👤 AKAUN SAYA\n\nID Telegram: {user_id}\nLangganan: {status}')
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


async def handle_image_or_receipt_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route uploaded image documents to the active flow, without breaking receipt PDFs."""
    if context.user_data.get('stage') == 'prompt_upload':
        await photo(update, context)
        return
    await receive_receipt(update, context)


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('busy'):
        await update.message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    if context.user_data.get('stage') == 'receipt_upload':
        await receive_receipt(update, context)
        return
    if context.user_data.get('stage') == 'prompt_upload':
        photo_item = update.message.photo[-1] if update.message.photo else update.message.document
        if not update.message.photo and not (update.message.document and (update.message.document.mime_type or '').startswith('image/')):
            await update.message.reply_text('Sila hantar fail imej produk (gambar).')
            return
        context.user_data['prompt_reference_photo'] = photo_item.file_id
        context.user_data['stage'] = 'prompt_library_details'
        await update.message.reply_text('✅ Gambar diterima sebagai rujukan utama. Sekarang tampal nama produk atau maklumat produk daripada Shopee. Nama sahaja memadai; tidak perlu pautan. Jika tidak mahu tambah maklumat, hantar tanda - .')
        return
    if context.user_data.get('stage') == 'prompt_photo':
        context.user_data['stage'] = 'prompt_product_name'
        await update.message.reply_text('📌 Klippo kini menggunakan prompt berasaskan nama produk sahaja. Gambar tidak diproses. Tampal nama produk daripada Shopee di sini.')
        return
    if context.user_data.get('stage') != 'photos':
        await update.message.reply_text('Pilih 📷 Upload Gambar dahulu melalui menu Video Transisi.', reply_markup=main_menu())
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
            message = f'✅ Video {len(clips)} diterima (urutan #{len(clips)}).\n\n📤 Terus hantar Video {len(clips) + 1} sebagai File / Document.'
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
            progress = await update.message.reply_text('⏳ DALAM PROSES — 0%\nMenyediakan fail video...')
            with tempfile.TemporaryDirectory(prefix='shopee_') as td:
                source = Path(td) / 'input.mp4'
                destination = Path(td) / 'shopee.mp4'
                await (await context.bot.get_file(item.file_id)).download_to_drive(source)
                await progress_update(progress, 40, 'Fail diterima. Sedang menukar format video...')
                await asyncio.to_thread(convert_shopee, source, destination)
                await progress_update(progress, 90, 'Penukaran selesai. Menghantar fail...')
                with destination.open('rb') as handle:
                    await update.message.reply_document(document=handle, filename='Klippo_Shopee_HQ.mp4', caption='✅ MP4 berkualiti tinggi. Muat turun sebagai fail untuk mengelakkan pemampatan tambahan. Kelulusan Shopee tertakluk pada peraturan platform.', reply_markup=main_menu())
                await progress_update(progress, 100, 'Video berjaya dihantar.')
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
        progress = None
        try:
            try:
                animation = await query.message.reply_animation(animation=fusion_gif(), caption='⏳ Dalam proses...')
            except Exception:
                logging.exception('Fusion animation unavailable')
            progress = await query.message.reply_text('⏳ DALAM PROSES — 0%\nMenyediakan video untuk gabungan...')
            with tempfile.TemporaryDirectory(prefix='merge_') as folder:
                paths = []
                for index, file_id in enumerate(context.user_data['merge_files']):
                    path = Path(folder) / f'input_{index}.mp4'
                    await (await context.bot.get_file(file_id)).download_to_drive(path)
                    paths.append(path)
                    await progress_update(progress, round(30 * (index + 1) / len(context.user_data['merge_files'])), 'Memuat turun klip...')
                output = Path(folder) / 'gabungan.mp4'
                await progress_update(progress, 40, 'Klip tersedia. Sedang menggabungkan video...')
                await asyncio.to_thread(merge_videos, paths, output, style)
                await progress_update(progress, 90, 'Gabungan selesai. Menghantar fail...')
                try:
                    if animation:
                        await animation.delete()
                        animation = None
                    success_animation = await query.message.reply_animation(animation=fusion_gif(True), caption='✅ Gabungan selesai!')
                except Exception:
                    logging.exception('Fusion completion display failed')
                with output.open('rb') as file:
                    await query.message.reply_document(document=file, filename='Klippo_Gabungan.mp4', caption='✅ Video siap digabung. Audio asal dikekalkan dan dipadankan dengan transisi.', reply_markup=main_menu(), write_timeout=240, read_timeout=120, connect_timeout=30)
                await progress_update(progress, 100, 'Video gabungan berjaya dihantar.')
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
    logging.info('KLIPPO callback action=%r stage=%r user=%s', action, context.user_data.get('stage'), update.effective_user.id)
    if action == 'home':
        if not context.user_data.get('busy'):
            reset(context)
        await query.message.reply_text('🏠 KLIPPO | Menu Utama\n\nPilih fungsi di bawah:', reply_markup=main_menu(update.effective_user.id))
        return
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
        context.user_data['stage'] = 'video_input'
        await query.message.reply_text('🎬 Upload 1–5 gambar produk dahulu. Selepas itu, salin dan tampal tajuk produk daripada Shopee.', reply_markup=video_input_menu())
    elif action == 'video_input:photos':
        context.user_data['stage'] = 'photos'
        await query.message.reply_text('📷 Hantar 1–5 gambar produk. Tekan Selesai apabila cukup.', reply_markup=photos_menu())
    elif action == 'video_input:shopee':
        context.user_data['stage'] = 'shopee_link'
        await query.message.reply_text('🔗 MASUKKAN PAUTAN PRODUK SHOPEE\n\n1. Buka aplikasi Shopee dan pilih produk.\n2. Tekan Kongsi → Salin Pautan.\n3. Tampal pautan halaman produk Shopee Malaysia yang lengkap dalam ruang menaip mesej di bawah.\n4. Tekan Hantar (➤).\n\nContoh format: https://shopee.com.my/product/123456/789012\n\n⏳ Selepas dihantar, KLIPPO akan cuba mengambil gambar awam produk secara automatik. Jika gagal, bot akan meminta gambar sendiri.\n\n👇 Tampal pautan sekarang:', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📷 Tukar kepada Upload Gambar', callback_data='video_input:back')], [InlineKeyboardButton('🏠 Menu Utama', callback_data='home')]]))
    elif action == 'video_input:back':
        context.user_data['stage'] = 'photos'
        context.user_data.pop('shopee_url', None)
        await query.message.reply_text('📷 Hantar 1–5 gambar produk. Tekan Selesai apabila cukup.', reply_markup=photos_menu())
    elif action == 'prompt':
        reset(context)
        context.user_data['prompt_mode'] = 'storyboard'
        context.user_data['prompt_style'] = 'auto'
        context.user_data['prompt_concept'] = ''
        context.user_data['stage'] = 'prompt_product_type'
        context.user_data['prompt_product_type'] = 'other'
        await query.message.reply_text(
            '✍️ KLIPPO ONE PROMPT — Pilih jenis produk dahulu supaya gaya iklan dan aksi lebih sesuai:',
            reply_markup=prompt_product_type_menu()
        )
    elif action.startswith('prompt_type:') and stage == 'prompt_type':
        selected = action.split(':', 1)[1]
        if selected == 'library':
            context.user_data['stage'] = 'prompt_library_details'
            await query.message.reply_text('🛍️ Tampal nama produk daripada Shopee. Gambar tidak diperlukan. Klippo akan mengesan jenis produk daripada nama, contohnya beg tangan, sling bag, beg galas atau dompet.')
        elif selected in ('normal', 'storyboard', 'doodle'):
            context.user_data['prompt_mode'] = 'storyboard' if selected == 'doodle' else selected
            context.user_data['stage'] = 'prompt_duration'
            await query.message.reply_text('⏱️ Pilih durasi prompt video:', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🎬 10 Saat', callback_data='prompt_duration:10'),
                 InlineKeyboardButton('🎞️ 20 Saat', callback_data='prompt_duration:20')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
            ]))
    elif action == 'prompt_categories':
        context.user_data['stage'] = 'prompt_category'
        await query.message.reply_text('📚 Pilih kategori produk:', reply_markup=prompt_category_menu())
    elif action.startswith('pcat:') and stage in ('prompt_category', 'prompt_category_options'):
        category_id = action.split(':', 1)[1]
        if category_id not in CATEGORIES_BY_ID:
            await query.message.reply_text('Kategori tidak ditemui. Sila pilih semula.', reply_markup=prompt_category_menu())
        else:
            context.user_data['prompt_category'] = category_id
            context.user_data['stage'] = 'prompt_category_options'
            await query.message.reply_text(
                f"🎬 Prompt siap — {CATEGORIES_BY_ID[category_id].get('label', category_id)}. Pilih gaya:",
                reply_markup=prompt_options_menu(category_id)
            )
    elif action.startswith('ptpl:') and stage == 'prompt_category_options':
        prompt_id = action.split(':', 1)[1]
        template = PROMPTS_BY_ID.get(prompt_id)
        category_id = context.user_data.get('prompt_category', '')
        if not template or template.get('category') != category_id:
            await query.message.reply_text(
                'Idea video tidak ditemui dalam kategori tersebut. Sila pilih semula.',
                reply_markup=prompt_options_menu(category_id)
            )
        else:
            # Curated entries are creative concepts for the same universal prompt,
            # not standalone prompt types.
            context.user_data['prompt_concept'] = (
                (template.get('label', '') + ': ' + template.get('description', '')).strip(': ')
            )
            if context.user_data.get('prompt_product_name'):
                product_name = context.user_data['prompt_product_name']
                subtype = detect_bag_subtype(product_name)
                context.user_data['prompt_bag_subtype'] = subtype
                if subtype == 'wallet' or category_id == 'wallets':
                    context.user_data['prompt_product_type'] = 'wallet'
                elif category_id == 'bags':
                    context.user_data['prompt_product_type'] = 'bag'
                context.user_data['stage'] = 'prompt_scene'
                await query.message.reply_text(
                    '✅ Nama produk: ' + product_name + '\n🔎 Jenis dikesan: ' + (subtype.replace('_', ' ') if subtype else category_id) + '\n\n🎨 Pilih latar video:',
                    reply_markup=prompt_scene_menu()
                )
            else:
                context.user_data['stage'] = 'prompt_product_name'
                await query.message.reply_text('🛍️ Masukkan nama produk daripada Shopee. Nama sahaja — gambar dan pautan tidak diperlukan.')
    elif action.startswith('prompt_product_type:'):
        # Handle the product callback even if the in-memory stage is stale.
        # Telegram callbacks can outlive a menu redraw or a session state change.
        selected = action.split(':', 1)[1]
        if selected in PRODUCT_TYPES:
            context.user_data['prompt_product_type'] = selected
            context.user_data['stage'] = 'prompt_duration'
            logging.info('KLIPPO product type selected=%s user=%s', selected, update.effective_user.id)
            await query.message.reply_text(
                f"🛍️ Jenis produk: {PRODUCT_TYPES[selected]}\n\n⏱️ Pilih tempoh video:",
                reply_markup=prompt_duration_menu()
            )
        else:
            await query.message.reply_text(
                'Pilihan produk tidak sah. Sila pilih semula:',
                reply_markup=prompt_product_type_menu()
            )
    elif action.startswith('prompt_duration:') and stage == 'prompt_duration':
        selected = action.split(':', 1)[1]
        if selected in ('10', '20'):
            context.user_data['prompt_duration'] = int(selected)
            context.user_data['stage'] = 'prompt_style'
            await query.message.reply_text(
                '🎨 Pilih gaya visual untuk prompt yang sama:',
                reply_markup=prompt_style_menu(context.user_data.get('prompt_product_type', 'other'))
            )
    elif action.startswith('prompt_style:') and stage == 'prompt_style':
        selected = action.split(':', 1)[1]
        valid = {'auto'} | {key for key, _ in storyboard_styles()}
        if selected in valid:
            context.user_data['prompt_style'] = selected
            context.user_data['stage'] = 'prompt_idea_choice'
            await query.message.reply_text(
                '💡 Mahu tambah satu idea aksi daripada koleksi prompt siap? Ia akan digabungkan ke dalam prompt yang sama.',
                reply_markup=prompt_idea_choice_menu()
            )
    elif action == 'prompt_idea:yes' and stage == 'prompt_idea_choice':
        context.user_data['stage'] = 'prompt_category'
        await query.message.reply_text(
            '📚 Pilih kategori untuk idea video (bukan prompt berasingan):',
            reply_markup=prompt_category_menu()
        )
    elif action == 'prompt_idea:skip' and stage == 'prompt_idea_choice':
        context.user_data['prompt_concept'] = ''
        context.user_data['stage'] = 'prompt_product_name'
        await query.message.reply_text('🛍️ Masukkan nama produk daripada Shopee. Buka Shopee, copy dan paste nama produk di sini. Nama sahaja — tidak perlu pautan.\n\nContoh: VELLA Beg Tangan Wanita Besar Sling Shoulder Women Luxury Handbags')
    elif action == 'prompt_input:photo' and stage == 'prompt_input':
        context.user_data['stage'] = 'prompt_product_name'
        await query.message.reply_text('🛍️ Mod prompt Klippo tidak menggunakan gambar atau analisis AI. Tampal nama produk sahaja untuk mengesan kategori secara automatik.')
    elif action.startswith('prompt_details:') and stage == 'prompt_details_choice':
        if action == 'prompt_details:add':
            context.user_data['stage'] = 'prompt_details_text'
            await query.message.reply_text('Masukkan maklumat tambahan produk (pilihan), seperti nama atau ciri penting:')
        elif action == 'prompt_details:skip':
            context.user_data['prompt_product'] = ''
            context.user_data['stage'] = 'prompt_scene'
            await query.message.reply_text('🎨 Pilih latar video:', reply_markup=prompt_scene_menu())
    elif action.startswith('scene:') and stage == 'prompt_scene':
        scenes = {
            'auto': 'clean premium studio background, selected to complement the named product',
            'studio': 'premium photography studio, soft neutral backdrop and realistic contact shadows',
            'dark': 'dark luxury studio, controlled rim lighting and understated premium contrast',
            'home': 'tasteful modern home interior, natural ambient lighting and believable product placement',
            'nature': 'restrained natural setting with soft daylight, without obscuring the product',
            'minimal': 'bright minimalist setting with clean neutral surfaces and soft daylight'
        }
        selected = action.split(':', 1)[1]
        if selected in scenes:
            context.user_data['prompt_scene'] = scenes[selected]
            context.user_data['stage'] = 'prompt_motion'
            if context.user_data.get('prompt_mode') == 'storyboard':
                action = 'motion:static' if context.user_data.get('prompt_style') == 'white_doodle' else 'motion:push'
            else:
                await query.message.reply_text('🎥 Pilih gerakan kamera:', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🔄 Orbit Terkawal', callback_data='motion:orbit')],
                [InlineKeyboardButton('🔍 Zoom Masuk', callback_data='motion:push')],
                [InlineKeyboardButton('↔️ Gerak Sisi', callback_data='motion:side')],
                [InlineKeyboardButton('✨ Studio Statik', callback_data='motion:static')]
            ]))
                return
    # Return only for actions handled by the first chain. Video workflow
    # callbacks must continue into the second chain.
    if action in ('admin_pending', 'admin', 'storyboard', 'make', 'prompt', 'prompt_categories') or action.startswith(
        ('admin_approve:', 'admin_reject:', 'prompt_type:', 'prompt_product_type:', 'prompt_duration:',
         'prompt_style:', 'prompt_idea:', 'prompt_details:', 'video_input:', 'prompt_input:', 'pcat:', 'ptpl:')
    ):
        return
    if action.startswith('motion:') and context.user_data.get('stage') == 'prompt_motion':
        motion = action.split(':', 1)[1]
        motions = {'orbit': 'A controlled 30-degree camera arc around the product, not a full 360-degree rotation; preserve the visible product geometry.', 'push': 'A slow forward dolly-in with gentle parallax; no object deformation.', 'side': 'A smooth left-to-right camera slide with stable product proportions.', 'static': 'A locked camera with subtle studio lighting changes only.'}
        if motion in motions:
            context.user_data['prompt_motion_choice'] = motion
            context.user_data['stage'] = 'prompt_confirm'
            style_key = context.user_data.get('prompt_style', 'auto')
            style_labels = dict(storyboard_styles())
            style_name = 'Auto (Disyorkan)' if style_key == 'auto' else style_labels.get(style_key, style_key)
            concept = context.user_data.get('prompt_concept', '').strip() or 'Tiada — tanpa idea tambahan'
            product_name = context.user_data.get('prompt_product_name', '').strip() or 'Tidak diisi'
            scene = context.user_data.get('prompt_scene', 'clean studio background')
            scene_labels = {
                'clean premium studio background, selected to complement the exact product reference': 'Auto — studio premium',
                'premium photography studio, soft neutral backdrop and realistic contact shadows': 'Studio Premium',
                'dark luxury studio, controlled rim lighting and understated premium contrast': 'Mewah Gelap',
                'tasteful modern home interior, natural ambient lighting and believable product placement': 'Ruang Rumah',
                'restrained natural setting with soft daylight, without obscuring the product': 'Alam Semula Jadi',
                'bright minimalist setting with clean neutral surfaces and soft daylight': 'Cerah Minimalis',
            }
            motion_labels = {'orbit': 'Orbit Terkawal', 'push': 'Zoom Masuk', 'side': 'Gerak Sisi', 'static': 'Studio Statik'}
            summary = chr(10).join([
                '🧾 SEMAK PILIHAN SEBELUM JANA PROMPT',
                '',
                f'🛍️ Nama produk: {product_name}',
                f'📦 Jenis produk: {PRODUCT_TYPES.get(context.user_data.get("prompt_product_type", "other"), "Produk lain")}',
                f'⏱️ Tempoh: {context.user_data.get("prompt_duration", 10)} saat',
                f'🎨 Gaya visual: {style_name}',
                f'💡 Idea video: {concept}',
                f'🖼️ Latar: {scene_labels.get(scene, scene)}',
                f'🎥 Gerakan kamera: {motion_labels[motion]}',
                '',
                'Semak semua pilihan di atas. Tekan Jana Prompt untuk meneruskan.'
            ])
            await query.message.reply_text(summary, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✅ Jana Prompt', callback_data='prompt_generate:confirm')],
                [InlineKeyboardButton('🔁 Mula Semula / Tukar Pilihan', callback_data='prompt')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
            ]))
    elif action == 'prompt_generate:confirm' and context.user_data.get('stage') == 'prompt_confirm':
        motion = context.user_data.get('prompt_motion_choice', 'push')
        motions = {'orbit': 'A controlled 30-degree camera arc around the product, not a full 360-degree rotation; preserve the visible product geometry.', 'push': 'A slow forward dolly-in with gentle parallax; no object deformation.', 'side': 'A smooth left-to-right camera slide with stable product proportions.', 'static': 'A locked camera with subtle studio lighting changes only.'}
        if motion in motions:
            waiting = await query.message.reply_text('⏳ DALAM PROSES — 0%' + chr(10) + 'Menyusun prompt...')
            try:
                product_name = context.user_data.get('prompt_product_name', '').strip()
                product = 'NAMA_PRODUK: ' + product_name + chr(10) + 'Optional user details: ' + context.user_data.get('prompt_product', '')
                scene = context.user_data.get('prompt_scene', 'clean studio background')
                style_choice = context.user_data.get('prompt_style', 'auto')
                if style_choice == 'auto':
                    subtype = context.user_data.get('prompt_bag_subtype', '')
                    style_choice = {
                        'wallet': 'wallet_luxury_macro',
                        'backpack': 'backpack_demo',
                        'sling_bag': 'sling_bag_lifestyle',
                        'handbag': 'handbag_showcase',
                        'bag': 'bag_tabletop_reveal',
                    }.get(subtype, 'auto')
                prompt = build_prompt(
                    'storyboard', product, scene, motions[motion],
                    style_choice,
                    context.user_data.get('prompt_duration', 10),
                    context.user_data.get('prompt_concept', ''),
                    product_type=context.user_data.get('prompt_product_type', 'other')
                )
                await progress_update(waiting, 70, 'Prompt siap disusun. Menghantar hasil...')
                context.user_data['stage'] = 'prompt_done'
                mode_name = context.user_data.get('prompt_mode', 'normal')
                actions = InlineKeyboardMarkup([
                    [InlineKeyboardButton('🤖 NexaBot', url='https://t.me/aigeneratornexa_bot?start=ref37141287'), InlineKeyboardButton('✨ Gemini', url='https://gemini.google.com/')],
                    [InlineKeyboardButton('✍️ Prompt Baharu', callback_data='prompt'), InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
                ])
                sections = prompt.split('=== KLIPPO PART 2 ===') if context.user_data.get('prompt_duration') == 20 else [prompt]
                for index, section in enumerate(sections, 1):
                    section = section.strip()
                    caption = ('Bahagian ' + str(index) + '/2 — jana klip 10 saat ini secara berasingan. '
                               + ('Gunakan bingkai akhir Bahagian 1 sebagai rujukan sambungan.' if index == 2 else
                                  'Simpan bingkai terakhir untuk sambungan Bahagian 2.')) if len(sections) == 2 else ''
                    if len(section) <= 3900:
                        await query.message.reply_text((caption + chr(10) * 2 if caption else '') + section, reply_markup=actions)
                    else:
                        prompt_file = BytesIO(section.encode('utf-8'))
                        prompt_file.name = f'KLIPPO_prompt_{mode_name}_part{index}.txt'
                        await query.message.reply_document(
                            document=prompt_file,
                            filename=prompt_file.name,
                            caption=caption or '📋 Prompt penuh dalam satu fail: buka → Select All → Copy.',
                            reply_markup=actions
                        )
                await progress_update(waiting, 100, 'Prompt berjaya dihantar.')
            except Exception:
                logging.exception('Klippo prompt generation failed')
                await query.message.reply_text('❌ Prompt tidak berjaya dijana. Sila tekan Jana Prompt sekali lagi. Jika masalah berulang, maklumkan admin Klippo.')
            finally:
                try:
                    await waiting.delete()
                except Exception:
                    pass
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
    elif action == 'photos_order' and stage in ('photos', 'duration', 'background'):
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
    elif action.startswith(('photo_up:', 'photo_down:', 'photo_remove:')) and stage in ('photos', 'duration', 'background'):
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
            if context.user_data.get('storyboard_mode'):
                context.user_data['stage'] = 'style'
                await query.message.reply_text(f'⏱️ {duration} saat dipilih. Pilih gaya storyboard:', reply_markup=style_menu())
            else:
                context.user_data['style'] = 'smooth'
                context.user_data['stage'] = 'motion'
                await query.message.reply_text(f'⏱️ {duration} saat dipilih. Pilih pergerakan produk:', reply_markup=motion_menu())
    elif action.startswith('motion:') and stage in ('motion', 'duration', 'music', 'confirm'):
        motion = action.split(':',1)[1]
        if motion in ('auto','stop','spin','smooth','hand','hero','minimal'):
            context.user_data['motion_choice'] = motion
            context.user_data['stage'] = 'music'
            await query.message.reply_text('✅ Pergerakan dipilih. Pilih muzik:',reply_markup=music_menu())
        else:
            await query.message.reply_text('Pilihan pergerakan tidak dikenali. Pilih semula:',reply_markup=motion_menu())
    elif action == 'motions' and stage in ('motion','music','doodle','confirm'):
        context.user_data['stage'] = 'motion'
        await query.message.reply_text('🎞️ Pilih pergerakan produk:',reply_markup=motion_menu())
    elif action == 'photos_done':
        if stage not in ('photos', 'duration', 'background') or not context.user_data.get('photos'):
            await query.message.reply_text('Hantar sekurang-kurangnya satu gambar dahulu.', reply_markup=photos_menu())
            return
        context.user_data['stage'] = 'product_description'
        await query.message.reply_text('📝 WAJIB: Buka produk di Shopee → salin TAJUK produk → tampal tajuk penuh di ruang mesej ini dan tekan Hantar. Tidak perlu pautan. Tajuk digunakan untuk tulisan video.')
    elif action == 'description:skip' and stage == 'product_description':
        await query.message.reply_text('📝 Tajuk produk Shopee wajib diisi. Sila salin dan tampal tajuk penuh produk di ruang mesej.')
    elif action.startswith('background:') and stage == 'background':
        choice = action.split(':', 1)[1]
        if choice in ('original', 'white', 'beige', 'dark', 'pastel', 'gradient', 'pattern', 'duotone', 'mist'):
            context.user_data['background'] = choice
            context.user_data['stage'] = 'duration'
            await query.message.reply_text('⏱️ Pilih durasi video:', reply_markup=duration_menu())
    elif action == 'styles' and stage in ('style', 'music', 'confirm', 'motion', 'doodle'):
        context.user_data['stage'] = 'style'
        await query.message.reply_text('🎨 Tukar gaya (pilihan). Smooth digunakan secara lalai:', reply_markup=style_menu())
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
            await query.message.reply_text(f"✅ Gaya {context.user_data['style']} dipilih.\nLangkah 3/4 — Pilih muzik:", reply_markup=music_menu())
    elif action == 'effects' and stage == 'confirm':
        context.user_data['stage'] = 'doodle'
        await query.message.reply_text('✨ Pilih efek video:', reply_markup=doodle_menu())
    elif action.startswith('doodle:') and stage == 'doodle':
        choice = action.split(':', 1)[1]
        if choice in DOODLE_OPTIONS:
            context.user_data['doodle_choice'] = choice
            context.user_data['stage'] = 'music'
            if context.user_data.get('storyboard_mode'):
                context.user_data['stage'] = 'music'
                await query.message.reply_text('✅ Efek storyboard: '+DOODLE_OPTIONS[choice]+'\nPilih muzik:', reply_markup=music_menu())
            else:
                context.user_data['stage'] = 'confirm'
                await query.message.reply_text('✅ Efek: '+DOODLE_OPTIONS[choice]+'\nSemak dan hasilkan video.', reply_markup=confirm_menu())
    elif action == 'music' and stage in ('music', 'confirm', 'doodle', 'motion'):
        context.user_data['stage'] = 'music'
        await query.message.reply_text('🎵 Pilih muzik:', reply_markup=music_menu())
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
            context.user_data['stage'] = 'doodle'
            await query.message.reply_text(('📎 Hantar MP3 sendiri. ' if choice == 'custom' else '✅ Muzik dipilih. ') + 'Pilih efek video (bayang produk automatik untuk latar studio):', reply_markup=doodle_menu())
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
        await query.message.reply_text('❓ FAQ KLIPPO\\n\\nTekan persoalan untuk melihat jawapan dan gambar contoh:', reply_markup=faq_menu())
    elif action.startswith('faq:'):
        try:
            index = int(action.split(':', 1)[1])
            title, answer, _ = FAQ_ITEMS[index]
        except (ValueError, IndexError):
            await query.message.reply_text('Soalan tidak ditemui.', reply_markup=faq_menu())
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton('↩️ Kembali ke FAQ', callback_data='help')],
            [InlineKeyboardButton('🏠 Menu Utama', callback_data='home')],
        ])
        picture = faq_example(index)
        try:
            await query.message.reply_photo(photo=picture, caption=f'❓ {title}\\n\\n{answer}', reply_markup=keyboard)
        finally:
            picture.close()
    elif action == 'check':
        await status(update, context)
    elif action == 'reset':
        await start(update, context)
    elif action == 'home':
        await start(update, context)
    else:
        logging.warning('Unhandled KLIPPO callback action=%r stage=%r', action, stage)
        await query.message.reply_text('Pilihan ini tidak lagi aktif. Gunakan butang terkini di bawah.', reply_markup=main_menu(update.effective_user.id))


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stage = context.user_data.get('stage')
    value = update.message.text.strip()
    if value in ('🏠 Menu Utama', 'Menu Utama', 'menu', 'MENU', '/menu'):
        await start(update, context)
        return
    if stage == 'prompt_library_details':
        details = '' if value in ('-', '—', 'tiada', 'Tiada') else value
        context.user_data['prompt_library_details'] = details[:1200]
        if details:
            context.user_data['prompt_product_name'] = details[:240]
            subtype = detect_bag_subtype(details)
            category_id = detect_prompt_library_category(details)
            context.user_data['prompt_bag_subtype'] = subtype
            context.user_data['prompt_detected_category'] = category_id
            if category_id == 'wallets':
                context.user_data['prompt_product_type'] = 'wallet'
            elif category_id == 'bags':
                context.user_data['prompt_product_type'] = 'bag'
            if category_id:
                context.user_data['prompt_category'] = category_id
                context.user_data['stage'] = 'prompt_category_options'
                await update.message.reply_text(
                    '🔎 Klippo mengesan jenis produk: ' + subtype.replace('_', ' ') + '. Pilih gaya video dalam koleksi ' + CATEGORIES_BY_ID[category_id].get('label', category_id) + ':',
                    reply_markup=prompt_options_menu(category_id)
                )
                return
        context.user_data['stage'] = 'prompt_category'
        await update.message.reply_text('📚 Nama produk diterima. Pilih koleksi prompt:', reply_markup=prompt_category_menu())
        return
    if stage == 'prompt_product_name':
        if len(value) < 2 or value.lower().startswith(('http://', 'https://')):
            await update.message.reply_text('⚠️ Masukkan nama produk sahaja. Buka Shopee, copy nama produk dan paste di sini; pautan tidak diperlukan.')
            return
        context.user_data['prompt_product_name'] = value[:240]
        bag_subtype = detect_bag_subtype(value)
        context.user_data['prompt_bag_subtype'] = bag_subtype
        if bag_subtype == 'wallet':
            context.user_data['prompt_product_type'] = 'wallet'
        elif bag_subtype in ('handbag', 'sling_bag', 'backpack', 'bag'):
            context.user_data['prompt_product_type'] = 'bag'
        if bag_subtype:
            context.user_data['prompt_concept'] = (context.user_data.get('prompt_concept', '') + ' | Product-name category detection: ' + bag_subtype.replace('_', ' ') + '. Use the matching visual style without guessing product features.').strip(' |')
        context.user_data['stage'] = 'prompt_scene'
        await update.message.reply_text('✅ Nama produk disimpan: ' + value[:240] + chr(10) * 2 + '📌 Gambar dan analisis AI tidak diperlukan. Klippo mengesan jenis produk daripada nama dan memilih arahan visual yang sesuai. Pilih latar video:', reply_markup=prompt_scene_menu())
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
            context.user_data['stage'] = 'video_input'
            await update.message.reply_text('🎬 Pilih cara masukkan produk:', reply_markup=video_input_menu())
        elif action == 'convert':
            reset(context)
            context.user_data['stage'] = 'convert'
            await update.message.reply_text('🔄 TUKAR FORMAT VIDEO\n\nTekan 📎 → File / Fail → pilih video MP4 asal. Bot akan memprosesnya secara automatik.', reply_markup=main_menu())
        elif action == 'prompt':
            reset(context)
            context.user_data['prompt_mode'] = 'storyboard'
            context.user_data['prompt_style'] = 'auto'
            context.user_data['prompt_concept'] = ''
            context.user_data['stage'] = 'prompt_product_type'
            context.user_data['prompt_product_type'] = 'other'
            await update.message.reply_text(
                '✍️ KLIPPO ONE PROMPT — Pilih jenis produk dahulu supaya gaya iklan dan aksi lebih sesuai:',
                reply_markup=prompt_product_type_menu()
            )
        elif action == 'subscription':
            await update.message.reply_text('💎 LANGGANAN KLIPPO\n\nPelan Penyokong Awal: RM5 / 30 hari, sehingga 30 video sebulan. Pengaktifan manual selepas resit disemak.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')]]))
        elif action == 'account':
            await account_info(update, context)
        elif action == 'help':
            await update.message.reply_text('❓ BANTUAN\n\nJana Video: hantar gambar, pilih gaya dan muzik.\nTukar Format: hantar MP4.\nVideo AI: upload gambar, tambah maklumat jika mahu, kemudian pilih latar dan gerakan kamera. Prompt digunakan bersama gambar di penjana video luar.')
        else:
            await start(update, context)
        return
    if stage == 'shopee_link' and _shopee_link(value):
        context.user_data['shopee_url'] = _shopee_link(value)
        context.user_data['stage'] = 'background'
        await update.message.reply_text('🔗 Pautan Shopee diterima. KLIPPO akan cuba mengambil foto awam produk tanpa Gemini. Jika akses disekat, bot akan meminta gambar sendiri. Pilih latar:', reply_markup=background_menu())
    elif stage == 'shopee_link':
        await update.message.reply_text('⚠️ Pautan tidak dikenali. Tampal URL halaman produk Shopee Malaysia yang lengkap (https://shopee.com.my/...).')
    elif stage == 'product_description':
        if len(value.strip()) < 5 or _shopee_link(value) or value.lower().startswith(('http://', 'https://')):
            await update.message.reply_text('⚠️ Tampal TAJUK produk Shopee (bukan pautan). Tajuk wajib diisi sebelum meneruskan.')
            return
        context.user_data['shopee_url'] = ''
        context.user_data['product_description'] = value[:1800]
        context.user_data['video_product_info'] = value[:600]
        context.user_data['stage'] = 'background'
        await update.message.reply_text('✅ Tajuk produk diterima. Pilih latar produk:',reply_markup=background_menu())
    elif stage == 'photos' and value.lower().startswith('produk:'):
        info = value.split(':', 1)[1].strip()[:100]
        context.user_data['video_product_info'] = info
        hook = verified_video_hook(info)
        await update.message.reply_text(('✅ Cadangan hook: ' + hook if hook else 'Maklumat produk tidak cukup jelas; video akan dijana tanpa hook.'), reply_markup=photos_menu())
    elif stage == 'prompt_shopee_link':
        link = _shopee_link(value)
        if not link:
            await update.message.reply_text('⚠️ Pautan tidak dikenali. Tampal URL halaman produk Shopee Malaysia yang lengkap.')
            return
        context.user_data['shopee_url'] = link
        context.user_data['prompt_product'] = 'Product reference URL (do not invent unverified specifications): ' + link
        context.user_data['prompt_vision'] = ''
        context.user_data['stage'] = 'prompt_details_text'
        await update.message.reply_text('✅ Pautan diterima. Untuk prompt yang tepat, masukkan nama produk dan ciri utama daripada halaman Shopee (contoh: jenama, model, warna). Pautan sahaja tidak menjamin AI boleh membaca halaman produk.')
    elif stage == 'prompt_details_text':
        context.user_data['prompt_product'] = value[:600]
        context.user_data['stage'] = 'prompt_scene'
        await update.message.reply_text('🎨 Maklumat disimpan. Pilih latar video:', reply_markup=prompt_scene_menu())
    elif stage == 'prompt_scene':
        await update.message.reply_text('🎨 Pilih latar menggunakan butang:', reply_markup=prompt_scene_menu())
    else:
        await update.message.reply_text('Gunakan butang menu di bawah.', reply_markup=main_menu())




def _shopee_link(value):
    """Only accept an explicit Shopee product URL; never fetch arbitrary pasted URLs."""
    from urllib.parse import urlparse
    for candidate in re.findall(r'https?://[^\\s<>]+', value):
        candidate = candidate.rstrip('.,);]')
        parsed = urlparse(candidate)
        host = (parsed.hostname or '').lower()
        if parsed.scheme == 'https' and (host == 'shopee.com.my' or host.endswith('.shopee.com.my')) and (re.search(r'/product/\\d+/\\d+', parsed.path) or re.search(r'-i\\.\\d+\\.\\d+', parsed.path)):
            return candidate
    return ''


def _shopee_public_photo(url, destination, description):
    """Best-effort public OG photo only; no login, private API or image AI."""
    from urllib.request import Request, urlopen
    from urllib.parse import urlparse
    from PIL import Image
    if not _shopee_link(url):
        return False
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0 KLIPPO/1.0'})
        with urlopen(req, timeout=7) as response:
            if not (response.geturl().startswith('https://shopee.com.my/') or response.geturl().startswith('https://www.shopee.com.my/')):
                return False
            if 'text/html' not in response.headers.get('Content-Type', '').lower():
                return False
            page = response.read(350000).decode('utf-8', 'replace')
        from html import unescape
        def meta(name):
            for tag in re.findall(r'<meta\\b[^>]*>', page, re.I):
                if re.search(r'(?:property|name)=[\\"\\\']'+re.escape(name)+r'[\\"\\\']', tag, re.I):
                    match = re.search(r'content=[\\"\\\']([^\\"\\\']+)', tag, re.I)
                    if match:
                        return unescape(match.group(1))
            return ''
        title, image_url = meta('og:title'), meta('og:image')
        words = [w.lower() for w in re.findall(r'[A-Za-z0-9]{4,}', description) if not w.isdigit()]
        if not title or not image_url or (words and not any(w in title.lower() for w in words[:8])):
            return False
        parsed = urlparse(image_url)
        if parsed.scheme != 'https' or not (parsed.hostname or '').lower().endswith(('.shopee.com.my', '.shopee.sg', '.shopeemobile.com', '.shopeeusercontent.com')):
            return False
        with urlopen(Request(image_url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=7) as response:
            if not response.headers.get('Content-Type', '').lower().startswith('image/'):
                return False
            data = response.read(6000001)
        if len(data) > 6000000:
            return False
        with Image.open(BytesIO(data)) as opened:
            opened.verify()
        with Image.open(BytesIO(data)) as opened:
            if min(opened.size) < 350:
                return False
            ImageOps.exif_transpose(opened).convert('RGB').save(destination, 'JPEG', quality=92)
        return True
    except Exception as exc:
        logging.info('Public Shopee image unavailable: %s', exc)
        return False

def validate_rendered_video(path, expected_duration):
    """Reject truncated/invalid MP4 before reporting success to a paying user."""
    if not path.is_file() or path.stat().st_size < 20_000:
        raise RuntimeError('Fail video kosong atau terlalu kecil.')
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries',
         'format=duration:stream=codec_type,width,height',
         '-of', 'json', str(path)],
        capture_output=True, text=True, timeout=25, check=True)
    metadata = json.loads(probe.stdout)
    duration = float(metadata.get('format', {}).get('duration') or 0)
    video_streams = [stream for stream in metadata.get('streams', [])
                     if stream.get('codec_type') == 'video']
    if not video_streams:
        raise RuntimeError('Fail output tidak mempunyai trek video.')
    stream = video_streams[0]
    if int(stream.get('width') or 0) < 480 or int(stream.get('height') or 0) < 720:
        raise RuntimeError('Resolusi video tidak mencapai tahap minimum.')
    if abs(duration - expected_duration) > max(.8, expected_duration*.08):
        raise RuntimeError('Tempoh video tidak lengkap.')
    return metadata


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    ids = context.user_data.get('photos', [])
    if ids and not context.user_data.get('video_product_info', '').strip() and not context.user_data.get('storyboard_mode'):
        await message.reply_text('📝 Tajuk produk Shopee wajib diisi. Sila lengkapkan langkah selepas Selesai Hantar Gambar.')
        return
    if not ids and not context.user_data.get('shopee_url'):
        await message.reply_text('Hantar gambar atau pautan produk Shopee dahulu.', reply_markup=main_menu())
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
    progress = await message.reply_text('⏳ DALAM PROSES — 0%\nMenyediakan fail...')
    try:
        with tempfile.TemporaryDirectory(prefix='telegram_video_') as td:
            folder = Path(td)
            paths = []
            for i, fid in enumerate(list(ids)):
                p = folder / f'{i}.jpg'
                await (await context.bot.get_file(fid)).download_to_drive(p)
                paths.append(p)
                await progress_update(progress, round(25 * (i + 1) / len(ids)), 'Memuat turun gambar...')
            if not paths and context.user_data.get('shopee_url'):
                product_photo = folder / 'shopee_product.jpg'
                available = await asyncio.to_thread(_shopee_public_photo, context.user_data['shopee_url'], product_photo, context.user_data.get('product_description', ''))
                if not available:
                    context.user_data['stage'] = 'photos'
                    await message.reply_text('⚠️ Shopee tidak menyediakan gambar awam yang dapat diakses atau disahkan untuk pautan ini. Sila hantar 1–5 gambar produk sendiri, kemudian tekan Selesai.', reply_markup=photos_menu())
                    return
                paths.append(product_photo)
                await progress_update(progress, 25, 'Gambar produk Shopee diterima...')
            # Optional vision reads the actual uploaded product photo before background removal.
            # Never make the video depend on an external AI service being available.
            image_label_info = ''
            if os.environ.get('GEMINI_API_KEY') and paths:
                verified_parts = []
                for photo_path in paths[:3]:
                    try:
                        vision = await describe_photo(photo_path.read_bytes())
                        if not vision:
                            continue
                        for line in vision.splitlines():
                            key, separator, value = line.partition(':')
                            if separator and key.strip() in ('NAMA_PRODUK', 'KATEGORI', 'TEKS_DISAHKAN', 'CIRI_VISUAL'):
                                value = value.strip()
                                if value and value.upper() not in ('TIADA', 'TIDAK PASTI', 'NONE'):
                                    if key.strip() == 'TEKS_DISAHKAN':
                                        verified_parts.extend(v.strip() for v in value.split(';') if v.strip())
                                    elif key.strip() == 'CIRI_VISUAL':
                                        verified_parts.extend(v.strip() for v in value.split(';') if v.strip())
                                    else:
                                        verified_parts.append(value)
                    except Exception:
                        logging.exception('Optional image label analysis failed')
                image_label_info = ' '.join(dict.fromkeys(verified_parts))[:240]
            supplied_info = context.user_data.get('video_product_info', '').strip()
            label_info = ' '.join(part for part in (supplied_info, image_label_info) if part)[:320]
            background = context.user_data.get('background', 'original')
            product_layers = []
            if background != 'original':
                for i, path in enumerate(paths):
                    prepared = folder / f'product_bg_{i}.png'
                    foreground_path = folder / f'product_cutout_{i}.png'
                    try:
                        await asyncio.to_thread(replace_background, path, prepared, background, foreground_path)
                    except ValueError as exc:
                        logging.warning('Background removal declined: %s', exc)
                        alternative = folder / f'shopee_alternative_{i}.jpg'
                        link = context.user_data.get('shopee_url', '')
                        description = context.user_data.get('product_description', '')
                        found = bool(link and await asyncio.to_thread(_shopee_public_photo, link, alternative, description))
                        if found:
                            try:
                                await asyncio.to_thread(replace_background, alternative, prepared, background, foreground_path)
                                paths[i] = prepared
                                product_layers.append((foreground_path, background))
                                continue
                            except ValueError:
                                logging.info('Shopee public thumbnail is also unsuitable for segmentation')
                        await message.reply_text('⚠️ Gambar ini terlalu kompleks untuk pengasingan produk yang selamat. KLIPPO akan menggunakan gambar asal tanpa menggantikannya dengan gambar produk lain yang belum disahkan.')
                        product_layers = []
                        paths = [folder / f'{j}.jpg' for j in range(len(ids))] if ids else [folder / 'shopee_product.jpg']
                        break
                    paths[i] = prepared
                    product_layers.append((foreground_path, background))
                await progress_update(progress, 30, 'Produk diasingkan dan latar baharu disediakan...')
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
                doodle = context.user_data.get('doodle_choice', 'auto')
            await progress_update(progress, 40, 'Bahan siap. Sedang render video...')
            loop = asyncio.get_running_loop()
            def render_progress(percent, detail):
                asyncio.run_coroutine_threadsafe(progress_update(progress, percent, detail), loop)
            await asyncio.to_thread(render_video, paths, result, music, selected_style, context.user_data.get('duration', 10), doodle, None, render_progress, product_layers if not context.user_data.get('storyboard_mode') else None, context.user_data.get('motion_choice','auto'), label_info)
            await asyncio.to_thread(validate_rendered_video, result, context.user_data.get('duration', 10))
            await progress_update(progress, 90, 'Video lulus semakan fail. Menghantar ke Telegram...')
            with result.open('rb') as f:
                await message.reply_video(video=f, caption='🎬 Video siap! Hantar gambar baharu untuk video seterusnya.', supports_streaming=True,
                                                 read_timeout=120, write_timeout=120)
        await progress_update(progress, 100, 'Video berjaya dihantar.')
        reset(context)
        await message.reply_text('Mahu buat video lagi? Hantar gambar baharu.', reply_markup=main_menu())
    except subprocess.CalledProcessError as exc:
        logging.error('KLIPPO FFmpeg failed: %s', (exc.stderr or str(exc))[-1800:])
        await message.reply_text('❌ Proses video gagal pada FFmpeg. Semak log KLIPPO FFmpeg failed di Render.')
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
    app.add_handler(CommandHandler('menu', start))
    app.add_handler(CommandHandler('admin', admin))
    app.add_handler(CommandHandler('reset', start))
    app.add_handler(CommandHandler('periksa', status))
    app.add_handler(CommandHandler('jana', generate, block=False))
    for style in STYLES:
        app.add_handler(CommandHandler(style, choose_style))
    app.add_handler(CallbackQueryHandler(buttons, pattern=r'^(photos_order|photos_undo|photos_more|photo_up:[0-4]|photo_down:[0-4]|photo_remove:[0-4]|duration:(10|15|20)|admin_pending|admin_approve:[0-9]+|admin_reject:[0-9]+|admin|receipt_upload|subscription_qr|make|video_input:(photos|shopee|back)|prompt_input:(photo|shopee|back)|storyboard|doodle:(auto|white|sparkle|motion|all|none)|convert|merge|merge_next|merge_done|merge_style:(fade|smoothleft|slideleft|zoomin)|prompt|prompt_type:(normal|storyboard|doodle|library)|prompt_categories|pcat:[a-z0-9_]+|ptpl:[a-z0-9_]+|prompt_duration:(10|20)|prompt_product_type:[a-z0-9_]+|prompt_style:[a-z0-9_]+|prompt_idea:(yes|skip)|prompt_details:(add|skip)|prompt_generate:confirm|description:skip|scene:(auto|studio|dark|home|nature|minimal)|motion:(orbit|push|side|static|auto|stop|spin|smooth|hand)|photos_done|background:(original|white|beige|dark|pastel|gradient|pattern|duotone|mist)|confirm|styles|music|music_previews|subscription|account|help|check|reset|home|preview:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|listen:(cinematic|energetic|happy|luxury|nature|beauty)|style:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|music:(auto|cinematic|energetic|happy|luxury|nature|beauty|none|custom))$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.MimeType('application/pdf'), handle_image_or_receipt_document))
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
        bootstrap_retries=5,  # Retry transient Telegram getMe / webhook gateway failures at startup.
    )

if __name__ == '__main__':
    main()
