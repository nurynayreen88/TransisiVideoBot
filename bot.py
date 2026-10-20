"""Telegram slideshow bot: no paid API, FFmpeg required on PATH."""
import asyncio
import html
import json
from io import BytesIO
import logging
import os
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
from gemini_storyboard import generate_storyboard
from gemini_storyboard_image import generate_storyboard_sheet, GeminiStoryboardImageError
from prompt_engine import build_prompt, creative_angle_instruction
from prompt_model_defaults import auto_prompt_model_defaults, image_model_direction
from prompt_copy import spoken_copy_direction
from prompt_catalog import choices as storyboard_styles
from caption_hashtags import generate_caption, hashtag_library_size

# Curated prompt library; kept separate from the existing video-generation engine.
PROMPT_LIBRARY_PATH = Path(__file__).resolve().parent / 'prompts' / 'prompt_library.json'
try:
    with PROMPT_LIBRARY_PATH.open('r', encoding='utf-8') as handle:
        PROMPT_LIBRARY = json.load(handle)
except (OSError, json.JSONDecodeError):
    logging.exception('Klippo prompt library could not be loaded')
    PROMPT_LIBRARY = {'categories': [], 'prompts': []}
# Optional additive quality overrides; never replace or shrink the master library.
PROMPT_OVERRIDES_PATH = Path(__file__).resolve().parent / 'prompts' / 'prompt_quality_overrides.json'
try:
    with PROMPT_OVERRIDES_PATH.open('r', encoding='utf-8') as handle:
        _prompt_overrides = json.load(handle).get('overrides', [])
    _base_prompts = {item.get('id'): item for item in PROMPT_LIBRARY.get('prompts', []) if isinstance(item, dict) and item.get('id')}
    for _override in _prompt_overrides:
        _target = _base_prompts.get(_override.get('id')) if isinstance(_override, dict) else None
        if _target is not None:
            for _field in ('prompt', 'storyboard'):
                if _field in _override:
                    _target[_field] = _override[_field]
except (OSError, json.JSONDecodeError):
    logging.exception('Klippo prompt-quality overrides could not be loaded; using the master library unchanged')
# Normalized, reusable prompt components. The legacy library remains the fallback/source text.
PROMPT_COMPONENT_TABLES_PATH = Path(__file__).resolve().parent / 'prompts' / 'prompt_component_tables.json'
try:
    with PROMPT_COMPONENT_TABLES_PATH.open('r', encoding='utf-8') as handle:
        PROMPT_COMPONENT_TABLES = json.load(handle)
    _component_tables = PROMPT_COMPONENT_TABLES.get('tables', {})
    _PROMPT_COMPONENTS_BY_ID = {
        item.get('id'): item
        for item in _component_tables.get('storyboard_components', [])
        if isinstance(item, dict) and item.get('id')
    }
    _PROMPT_COMPONENT_MAP_BY_ID = {
        item.get('id'): item
        for item in _component_tables.get('prompt_component_map', [])
        if isinstance(item, dict) and item.get('id')
    }
except (OSError, json.JSONDecodeError):
    logging.exception('Klippo prompt component tables could not be loaded; using legacy storyboards')
    PROMPT_COMPONENT_TABLES = {'tables': {}}
    _PROMPT_COMPONENTS_BY_ID = {}
    _PROMPT_COMPONENT_MAP_BY_ID = {}


def _prompt_library_storyboard(template):
    """Resolve storyboard directions from normalized tables, with a safe legacy fallback."""
    if not isinstance(template, dict):
        return []
    mapping = _PROMPT_COMPONENT_MAP_BY_ID.get(template.get('id'))
    original = template.get('storyboard', [])
    if not isinstance(mapping, dict) or not isinstance(original, list) or len(original) != 4:
        return original
    fields = (
        ('hook_component_id', 0),
        ('action_component_id', 1),
        ('detail_component_id', 2),
        ('closing_component_id', 3),
    )
    resolved = []
    for field, index in fields:
        component = _PROMPT_COMPONENTS_BY_ID.get(mapping.get(field))
        if not isinstance(component, dict) or not component.get('direction'):
            return original
        shot = dict(original[index])
        direction = str(component['direction'])
        # Some legacy entries repeat their own time/shot label inside the direction.
        # The prompt engine adds the canonical timing separately, so remove only
        # this redundant prefix while preserving the actual shot instruction.
        direction = re.sub(r'^\s*\d+(?:[–-]\d+)?s\s*\|\s*[^:]{1,80}:\s*', '', direction)
        shot['direction'] = direction
        resolved.append(shot)
    return resolved


def _prompt_library_component_rules(template_id, audio_enabled=True, voiceover_mode='none', prompt_language='Malay', on_screen_text='no', camera_choice='auto'):
    """Assemble concise, choice-aware safety/audio rules from normalized component tables."""
    mapping = _PROMPT_COMPONENT_MAP_BY_ID.get(template_id)
    if not isinstance(mapping, dict):
        return ''
    tables = PROMPT_COMPONENT_TABLES.get('tables', {})

    def directions(table_name, ids):
        by_id = {
            item.get('id'): item for item in tables.get(table_name, [])
            if isinstance(item, dict) and item.get('id')
        }
        return [str(by_id[item_id].get('direction', '')).strip() for item_id in ids
                if item_id in by_id and by_id[item_id].get('direction')]

    rules = []
    camera_by_id = {
        item.get('id'): item for item in tables.get('camera_profiles', [])
        if isinstance(item, dict) and item.get('id')
    }
    camera_ids = mapping.get('camera_profile_ids', [])
    selected_camera_by_choice = {
        'push': 'camera_slow_push', 'dolly': 'camera_slow_push',
        'side': 'camera_lateral_slide', 'orbit': 'camera_limited_arc',
        'static': 'camera_locked',
    }
    selected_camera_id = selected_camera_by_choice.get(str(camera_choice or 'auto').casefold())
    if not selected_camera_id and str(camera_choice or 'auto').casefold() == 'auto':
        selected_camera_id = next(
            (item_id for item_id in camera_ids if item_id != 'camera_reference_safe'),
            'camera_reference_safe',
        )
    if selected_camera_id and selected_camera_id in camera_by_id:
        rules.append('CAMERA PROFILE: ' + str(camera_by_id[selected_camera_id].get('direction', '')).strip())
    safety_camera = camera_by_id.get('camera_reference_safe', {})
    if safety_camera and selected_camera_id != 'camera_reference_safe':
        rules.append('CAMERA SAFETY: ' + str(safety_camera.get('direction', '')).strip())

    hook_ids = mapping.get('hook_rule_ids', [])
    hook_rules = directions('hook_rules', hook_ids)
    if hook_rules:
        rules.append('HOOK: ' + hook_rules[0])

    if audio_enabled:
        language_key = 'audio_voice_english' if str(prompt_language or 'Malay').casefold() == 'english' else 'audio_voice_malay'
        if voiceover_mode == 'none':
            audio_key = 'audio_music_sfx_only'
        else:
            audio_key = language_key
        audio_by_id = {item.get('id'): item for item in tables.get('audio_profiles', []) if isinstance(item, dict)}
        audio = audio_by_id.get(audio_key, {})
        # An exact user script may be in a language different from the UI default;
        # retain music/SFX guidance but do not impose a conflicting voice language.
        audio_fields = ('music', 'sfx') if voiceover_mode == 'script' else ('voice', 'music', 'sfx')
        audio_parts = [audio.get(key, '') for key in audio_fields if audio.get(key)]
        if voiceover_mode == 'script':
            audio_parts.append('Use the supplied script exactly; do not add spoken lines or an extra spoken CTA.')
        elif voiceover_mode == 'none':
            audio_parts.append('Do not add voiceover or dialogue.')
        if audio_parts:
            rules.append('AUDIO: ' + ' '.join(audio_parts))

    cta_key = 'cta_soft_invitation' if audio_enabled and voiceover_mode == 'ai' else 'cta_no_added_dialogue'
    cta_rules = directions('cta_rules', [cta_key])
    if cta_rules:
        rules.append('CTA: ' + cta_rules[0])

    fidelity_ids = list(mapping.get('product_fidelity_rule_ids', []))
    if on_screen_text == 'yes':
        fidelity_ids = [item_id for item_id in fidelity_ids if item_id != 'no_text_watermark']
    fidelity_rules = directions('product_fidelity_rules', fidelity_ids)
    if fidelity_rules:
        rules.append('PRODUCT FIDELITY: ' + ' '.join(fidelity_rules))
    return '\n'.join(rules)


PROMPTS_BY_ID = {item['id']: item for item in PROMPT_LIBRARY.get('prompts', []) if isinstance(item, dict) and item.get('id')}
CATEGORIES_BY_ID = {item['id']: item for item in PROMPT_LIBRARY.get('categories', []) if isinstance(item, dict) and item.get('id')}
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
# HTTP client INFO logs include Telegram API URLs containing the bot token.
# Keep request URLs out of persistent hosting logs; retain application warnings/errors.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
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
    'navy': (34, 51, 79),
    'sage': (184, 199, 177),
    'sky': (190, 218, 235),
    'lavender': (209, 198, 231),
    'rose': (226, 184, 187),
    'mint': (190, 221, 207),
    'terracotta': (190, 112, 83),
    'charcoal': (49, 51, 56),
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
        'sky_gradient': ((245, 250, 255), (151, 194, 222)),
        'lavender_gradient': ((250, 246, 255), (190, 174, 222)),
        'sage_gradient': ((246, 249, 239), (159, 181, 151)),
        'blush_gradient': ((255, 246, 243), (225, 173, 178)),
        'midnight_gradient': ((91, 99, 121), (19, 24, 38)),
        'sand_gradient': ((255, 249, 235), (193, 157, 115)),
        'ocean_gradient': ((226, 247, 250), (28, 105, 139)),
        'forest_gradient': ((230, 240, 222), (39, 83, 62)),
        'sunset_gradient': ((255, 224, 195), (172, 77, 107)),
        'aurora_gradient': ((215, 247, 237), (95, 90, 165)),
        'mocha_gradient': ((246, 231, 211), (112, 78, 61)),
        'peach_gradient': ((255, 235, 220), (232, 151, 126)),
        'ice_gradient': ((248, 253, 255), (157, 202, 225)),
        'emerald_gradient': ((220, 245, 231), (22, 112, 86)),
        'plum_gradient': ((246, 226, 246), (104, 54, 111)),
        'coral_gradient': ((255, 231, 221), (213, 94, 91)),
        'graphite_gradient': ((115, 122, 133), (25, 29, 37)),
        'champagne_gradient': ((255, 250, 226), (192, 157, 91)),
        'lemon_gradient': ((255, 255, 219), (215, 205, 105)),
        'teal_gradient': ((218, 246, 242), (28, 112, 117)),
        'lilac_gradient': ((250, 239, 255), (164, 133, 202)),
        'cobalt_gradient': ((224, 237, 255), (42, 74, 160)),
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


def replace_background(source: Path, destination: Path, choice: str, foreground_destination: Path | None = None, custom_background_path: Path | None = None) -> Path:
    if choice not in BACKGROUNDS and choice not in ('gradient', 'pattern', 'duotone', 'mist', 'sky_gradient', 'lavender_gradient', 'sage_gradient', 'blush_gradient', 'midnight_gradient', 'sand_gradient', 'ocean_gradient', 'forest_gradient', 'sunset_gradient', 'aurora_gradient', 'mocha_gradient', 'peach_gradient', 'ice_gradient', 'emerald_gradient', 'plum_gradient', 'coral_gradient', 'graphite_gradient', 'champagne_gradient', 'lemon_gradient', 'teal_gradient', 'lilac_gradient', 'cobalt_gradient', 'custom'):
        raise ValueError('Unknown background')
    if choice == 'custom' and (custom_background_path is None or not custom_background_path.is_file()):
        raise ValueError('Custom background image is missing')
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
    if choice == 'custom':
        with Image.open(custom_background_path) as opened_background:
            background_image = ImageOps.exif_transpose(opened_background).convert('RGB')
        background_image = ImageOps.fit(background_image, foreground.size, method=Image.Resampling.LANCZOS)
        background = background_image.convert('RGBA')
    else:
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
    'bag': '👜 Beg / Dompet',
    'hijab': '🧕 Tudung / Hijab',
    'shoes': '👟 Kasut / Sandal',
    'beauty': '💄 Kecantikan / Skincare',
    'food': '🍰 Makanan / Minuman',
    'gadget': '📱 Gajet / Elektronik',
    'equipment': '🔌 Peralatan Elektrik / Perkakas',
    'home': '🏡 Rumah / Dapur',
    'accessory': '⌚ Aksesori / Barang Kemas',
    'toy': '🧸 Mainan / Permainan',
    'book_stationery': '📚 Buku / Alat Tulis',
    'sports': '⚽ Sukan / Kecergasan',
    'pet': '🐾 Haiwan Peliharaan',
    'automotive': '🚗 Aksesori Kereta / Motosikal',
    'baby': '🍼 Produk Bayi',
    'travel': '🧳 Kembara / Beg Perjalanan',
    'office': '🖇️ Pejabat / Organisasi',
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


def detect_product_subtype(product_name: str) -> str:
    """Infer a curated prompt subtype from product-name text only; never calls AI or image analysis."""
    name = (product_name or '').casefold()
    rules = [
        ('beauty', 'lip_gloss', ('lip gloss', 'lipgloss')),
        ('beauty', 'lipstick', ('lipstick', 'lip stick', 'gincu')),
        ('beauty', 'facial_cleanser', ('facial cleanser', 'face cleanser', 'cleanser', 'pencuci muka', 'sabun muka', 'pencuci wajah', 'face wash')),
        ('beauty', 'powder', ('face powder', 'loose powder', 'compact powder', 'setting powder', 'bedak', 'cushion powder')),
        ('beauty', 'serum', ('serum', 'ampoule')),
        ('beauty', 'sunscreen', ('sunscreen', 'sun screen', 'sunblock', 'spf')),
        ('beauty', 'mascara', ('mascara', 'maskara')),
        ('beauty', 'perfume', ('perfume', 'fragrance', 'minyak wangi', 'eau de parfum', 'eau de toilette')),
        ('beauty', 'moisturizer', ('moisturizer', 'moisturiser', 'moisturizing cream', 'pelembap', 'moisture cream')),
        ('beauty', 'toner', ('toner', 'facial mist')),
        ('beauty', 'blush', ('blush', 'blusher', 'rouge', 'pemerah pipi')),
        ('beauty', 'sheet_mask', ('sheet mask', 'masker muka', 'face mask')),
        ('clothing', 'hijab', ('hijab', 'tudung', 'shawl', 'bawal')),
        ('clothing', 'baju_kurung', ('baju kurung', 'kurung moden', 'kurung kedah')),
        ('clothing', 'dress', ('dress', 'gown', 'maxi dress')),
        ('clothing', 'shirt', ('shirt', 'blouse', 'kemeja', 'baju lelaki', 't-shirt', 'tshirt')),
        ('shoes', 'running_shoes', ('running shoes', 'kasut larian', 'jogging shoes')),
        ('shoes', 'sneakers', ('sneaker', 'trainers', 'kasut sukan')),
        ('shoes', 'heels', ('high heels', 'heels', 'kasut tumit', 'stiletto')),
        ('shoes', 'sandals', ('sandals', 'sandal', 'selipar', 'slippers')),
        ('gadgets', 'earbuds', ('earbuds', 'ear buds', 'wireless earphone', 'bluetooth earphone', 'earphones', 'earphone')),
        ('gadgets', 'phone_stand', ('phone stand', 'phone holder', 'stand telefon', 'holder telefon')),
        ('gadgets', 'smartwatch', ('smartwatch', 'smart watch', 'jam pintar')),
        ('gadgets', 'keyboard', ('keyboard', 'papan kekunci')),
        ('gadgets', 'powerbank', ('power bank', 'powerbank', 'portable charger')),
        ('home', 'kitchen_organizer', ('kitchen organizer', 'kitchen rack', 'rak dapur', 'organizer dapur')),
        ('home', 'cleaning_tool', ('mop', 'brush cleaner', 'cleaning brush', 'alat pembersih', 'penyapu', 'squeegee')),
        ('home', 'bedding', ('bedsheet', 'bed sheet', 'bedding', 'cadar', 'comforter', 'sarung bantal')),
        ('home', 'lamp', ('lampu', 'desk lamp', 'table lamp', 'night lamp', 'lamp')),
        ('accessories', 'watch', ('wristwatch', 'watch women', 'watch men', 'jam tangan')),
        ('accessories', 'earrings', ('earring', 'earrings', 'anting-anting', 'anting')),
        ('accessories', 'necklace', ('necklace', 'pendant', 'kalung', 'rantai leher')),
        ('accessories', 'sunglasses', ('sunglasses', 'sun glasses', 'cermin mata hitam')),
        ('food', 'snack', ('snack', 'kerepek', 'chips', 'crackers', 'snek')),
        ('food', 'drink', ('drink', 'beverage', 'juice', 'jus', 'kopi', 'coffee', 'tea', 'teh', 'minuman')),
        ('food', 'sauce', ('sauce', 'sos', 'sambal', 'condiment')),
        ('food', 'biscuits', ('biscuit', 'biscuits', 'cookies', 'biskut')),
        ('stationery', 'pen', ('pen ', 'ballpoint', 'ball pen', 'gel pen', 'fountain pen')),
        ('stationery', 'notebook', ('notebook', 'journal', 'buku nota', 'notepad')),
        ('stationery', 'marker', ('marker', 'highlighter', 'pen marker')),
        ('stationery', 'pencil_case', ('pencil case', 'pencil pouch', 'bekas pensel', 'kotak pensel')),
        ('sports', 'sports_gear', ('sports gear', 'football', 'soccer ball', 'badminton racket', 'racket badminton', 'dumbbell', 'skipping rope', 'jump rope', 'gym equipment', 'gym bag', 'beg sukan')),
        ('sports', 'water_bottle', ('sports bottle', 'water bottle', 'botol air')),
        ('sports', 'yoga_mat', ('yoga mat', 'alas yoga')),
        ('sports', 'resistance_band', ('resistance band', 'exercise band', 'getah senaman')),
        ('travel', 'luggage', ('luggage', 'suitcase', 'beg pakaian', 'beg travel', 'travel bag', 'cabin bag')),
        ('travel', 'packing_cubes', ('packing cube', 'packing cubes', 'travel organizer')),
        ('travel', 'travel_pillow', ('travel pillow', 'neck pillow', 'bantal travel')),
        ('travel', 'passport_holder', ('passport holder', 'pemegang pasport')),
        ('travel', 'toiletry_bag', ('toiletry bag', 'beg toiletries', 'beg mandian')),
        ('travel', 'luggage_tag', ('luggage tag', 'tag bagasi')),
        ('pets', 'pet_bed', ('pet bed', 'cat bed', 'dog bed', 'katil kucing', 'katil anjing')),
        ('pets', 'pet_leash', ('pet leash', 'dog leash', 'tali anjing', 'tali haiwan')),
        ('pets', 'pet_feeder', ('pet feeder', 'pet bowl', 'cat feeder', 'dog feeder', 'mangkuk haiwan')),
        ('pets', 'pet_toy', ('pet toy', 'cat toy', 'dog toy', 'mainan kucing', 'mainan anjing')),
        ('pets', 'grooming_brush', ('pet grooming brush', 'cat brush', 'dog brush', 'berus bulu haiwan')),
        ('pets', 'pet_carrier', ('pet carrier', 'cat carrier', 'dog carrier', 'beg pembawa haiwan')),
        ('automotive', 'phone_mount', ('car phone mount', 'car phone holder', 'pemegang telefon kereta')),
        ('automotive', 'car_organizer', ('car organizer', 'car organiser', 'car storage', 'organizer kereta')),
        ('automotive', 'car_vacuum', ('car vacuum', 'vacuum kereta', 'vakum kereta')),
        ('automotive', 'sunshade', ('car sunshade', 'sun shade kereta', 'pelindung matahari kereta')),
        ('automotive', 'car_diffuser', ('car diffuser', 'car air freshener', 'pewangi kereta')),
        ('automotive', 'seat_cushion', ('car seat cushion', 'cushion kereta', 'kusyen kereta')),
        ('garden', 'planter', ('planter pot', 'plant pot', 'pasu bunga', 'pasu tanaman')),
        ('garden', 'watering_can', ('watering can', 'penyiram pokok', 'bekas siram')),
        ('garden', 'gardening_gloves', ('gardening gloves', 'garden gloves', 'sarung tangan kebun')),
        ('garden', 'pruning_shears', ('pruning shears', 'secateurs', 'gunting pokok')),
        ('garden', 'grow_light', ('grow light', 'plant light', 'lampu tanaman')),
        ('garden', 'plant_stand', ('plant stand', 'rak pasu', 'stand pasu')),
        ('kitchen', 'lunchbox', ('lunchbox', 'lunch box', 'bekas makanan')),
        ('kitchen', 'cookware', ('cookware', 'frying pan', 'saucepan', 'periuk', 'kuali')),
        ('kitchen', 'spice_rack', ('spice rack', 'rak rempah')),
        ('kitchen', 'cutting_board', ('cutting board', 'chopping board', 'papan pemotong')),
        ('kitchen', 'tumbler', ('tumbler', 'travel tumbler', 'bekas minuman')),
        ('kitchen', 'small_appliance', ('air fryer', 'blender', 'toaster', 'rice cooker', 'coffee maker')),
        ('furniture', 'chair', ('dining chair', 'office chair', 'kerusi')),
        ('furniture', 'side_table', ('side table', 'meja sisi')),
        ('furniture', 'bookshelf', ('bookshelf', 'book shelf', 'rak buku')),
        ('furniture', 'desk', ('writing desk', 'study desk', 'meja belajar', 'meja kerja')),
        ('furniture', 'drawer_organizer', ('drawer organizer', 'drawer organiser', 'organizer laci')),
        ('furniture', 'decor_mirror', ('decor mirror', 'wall mirror', 'cermin dinding')),
        ('baby', 'diaper_bag', ('diaper bag', 'beg lampin')),
        ('baby', 'baby_blanket', ('baby blanket', 'selimut bayi')),
        ('baby', 'baby_bottle', ('baby bottle', 'botol susu bayi')),
        ('baby', 'high_chair', ('high chair', 'kerusi makan bayi')),
        ('baby', 'soft_toy', ('soft toy', 'plush toy', 'boneka lembut')),
        ('baby', 'stroller_accessory', ('stroller accessory', 'aksesori stroller')),
        ('crafts', 'yarn', ('yarn', 'benang kait')),
        ('crafts', 'crochet_kit', ('crochet kit', 'set mengait')),
        ('crafts', 'beads', ('craft beads', 'manik kraf')),
        ('crafts', 'paint_set', ('paint set', 'watercolor set', 'set cat air')),
        ('crafts', 'sewing_kit', ('sewing kit', 'set jahitan')),
        ('crafts', 'clay_tools', ('clay tools', 'alat tanah liat')),
    ]
    for category, subtype, keywords in rules:
        if any(keyword in name for keyword in keywords):
            return subtype
    bag_subtype = detect_bag_subtype(name)
    if bag_subtype:
        return bag_subtype
    return ''


def detect_prompt_library_category(product_name: str) -> str:
    """Map common product-name keywords to a curated GitHub prompt-library category."""
    subtype = detect_product_subtype(product_name)
    category_by_subtype = {
        'lip_gloss': 'beauty', 'lipstick': 'beauty', 'facial_cleanser': 'beauty',
        'powder': 'beauty', 'serum': 'beauty', 'sunscreen': 'beauty', 'mascara': 'beauty',
        'perfume': 'beauty', 'moisturizer': 'beauty', 'toner': 'beauty', 'blush': 'beauty',
        'sheet_mask': 'beauty', 'hijab': 'clothing', 'baju_kurung': 'clothing',
        'dress': 'clothing', 'shirt': 'clothing', 'running_shoes': 'shoes',
        'sneakers': 'shoes', 'heels': 'shoes', 'sandals': 'shoes', 'earbuds': 'gadgets',
        'phone_stand': 'gadgets', 'smartwatch': 'gadgets', 'keyboard': 'gadgets',
        'powerbank': 'gadgets', 'kitchen_organizer': 'home', 'cleaning_tool': 'home',
        'bedding': 'home', 'lamp': 'home', 'watch': 'accessories', 'earrings': 'accessories',
        'necklace': 'accessories', 'sunglasses': 'accessories', 'snack': 'food',
        'drink': 'food', 'sauce': 'food', 'biscuits': 'food', 'pen': 'stationery',
        'notebook': 'stationery', 'marker': 'stationery', 'pencil_case': 'stationery',
        'sports_gear': 'sports', 'water_bottle': 'sports', 'yoga_mat': 'sports', 'resistance_band': 'sports',
        'luggage': 'travel', 'packing_cubes': 'travel', 'travel_pillow': 'travel', 'passport_holder': 'travel', 'toiletry_bag': 'travel', 'luggage_tag': 'travel',
        'pet_bed': 'pets', 'pet_leash': 'pets', 'pet_feeder': 'pets', 'pet_toy': 'pets', 'grooming_brush': 'pets', 'pet_carrier': 'pets',
        'phone_mount': 'automotive', 'car_organizer': 'automotive', 'car_vacuum': 'automotive', 'sunshade': 'automotive', 'car_diffuser': 'automotive', 'seat_cushion': 'automotive',
        'planter': 'garden', 'watering_can': 'garden', 'gardening_gloves': 'garden', 'pruning_shears': 'garden', 'grow_light': 'garden', 'plant_stand': 'garden',
        'lunchbox': 'kitchen', 'cookware': 'kitchen', 'spice_rack': 'kitchen', 'cutting_board': 'kitchen', 'tumbler': 'kitchen', 'small_appliance': 'kitchen',
        'chair': 'furniture', 'side_table': 'furniture', 'bookshelf': 'furniture', 'desk': 'furniture', 'drawer_organizer': 'furniture', 'decor_mirror': 'furniture',
        'diaper_bag': 'baby', 'baby_blanket': 'baby', 'baby_bottle': 'baby', 'high_chair': 'baby', 'soft_toy': 'baby', 'stroller_accessory': 'baby',
        'yarn': 'crafts', 'crochet_kit': 'crafts', 'beads': 'crafts', 'paint_set': 'crafts', 'sewing_kit': 'crafts', 'clay_tools': 'crafts',
        'wallet': 'wallets', 'backpack': 'bags', 'sling_bag': 'bags',
        'handbag': 'bags', 'bag': 'bags',
    }
    return category_by_subtype.get(subtype, '')


def prompt_flow_menu():
    # Legacy helper: never show the old two-choice prompt menu.
    return InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]])


def prompt_images_start_menu():
    # Before the first image arrives, show only the option to return home.
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_images_menu():
    # Show the completion button only after at least one image has arrived.
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Selesai Hantar Gambar', callback_data='prompt_images_done')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def _prompt_is_animal_related(user_data):
    """Show animal-model controls for pet products without changing unrelated flows."""
    category = str(user_data.get('prompt_product_type', '')).casefold()
    subtype = str(user_data.get('prompt_product_subcategory', '')).casefold()
    name = ' '.join(str(user_data.get(key, '') or '') for key in (
        'prompt_product_name', 'prompt_library_details',
        'prompt_custom_category_name', 'prompt_custom_subcategory_name'
    )).casefold()
    animal_terms = (
        'pet', 'pets', 'kucing', 'cat food', 'cat toy', 'cat bed', 'cat litter',
        'anjing', 'dog food', 'dog toy', 'dog bed', 'puppy', 'kitten',
        'hamster', 'rabbit', 'arnab', 'burung', 'bird cage', 'fish tank',
        'aquarium', 'makanan haiwan', 'haiwan peliharaan', 'tali anjing',
        'tali kucing', 'pasir kucing', 'pet carrier', 'pet feeder', 'pet leash'
    )
    return category in {'pet', 'pets'} or subtype.startswith(('pet_', 'pets_')) or any(term in name for term in animal_terms)


def prompt_model_presence_menu(user_data=None):
    buttons = [
        [InlineKeyboardButton('👩 Ada Model Manusia', callback_data='prompt_model:yes')],
    ]
    if user_data and _prompt_is_animal_related(user_data):
        buttons.append([InlineKeyboardButton('🐾 Haiwan sebagai model', callback_data='prompt_model:animal')])
    buttons.extend([
        [InlineKeyboardButton('📦 Tiada Model — Fokus Produk', callback_data='prompt_model:none')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])
    return InlineKeyboardMarkup(buttons)


def prompt_animal_species_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Auto — ikut produk', callback_data='prompt_animal_species:auto')],
        [InlineKeyboardButton('🐱 Kucing', callback_data='prompt_animal_species:cat'),
         InlineKeyboardButton('🐶 Anjing', callback_data='prompt_animal_species:dog')],
        [InlineKeyboardButton('🐰 Arnab', callback_data='prompt_animal_species:rabbit'),
         InlineKeyboardButton('🐦 Burung', callback_data='prompt_animal_species:bird')],
        [InlineKeyboardButton('🐹 Hamster', callback_data='prompt_animal_species:hamster'),
         InlineKeyboardButton('🐠 Ikan', callback_data='prompt_animal_species:fish')],
        [InlineKeyboardButton('🐴 Kuda', callback_data='prompt_animal_species:horse')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_model_count_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('1 model', callback_data='prompt_model_count:1'),
         InlineKeyboardButton('2 model', callback_data='prompt_model_count:2')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_model_gender_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Auto — ikut produk', callback_data='prompt_model_gender:auto')],
        [InlineKeyboardButton('Wanita', callback_data='prompt_model_gender:female'),
         InlineKeyboardButton('Lelaki', callback_data='prompt_model_gender:male')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_model_hijab_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Bertudung', callback_data='prompt_model_hijab:hijab')],
        [InlineKeyboardButton('Tidak bertudung', callback_data='prompt_model_hijab:no_hijab')],
    ])


def prompt_model_ethnicity_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Melayu', callback_data='prompt_model_ethnicity:Malay'),
         InlineKeyboardButton('Cina', callback_data='prompt_model_ethnicity:Chinese')],
        [InlineKeyboardButton('India', callback_data='prompt_model_ethnicity:Indian')],
        [InlineKeyboardButton('Rawak — kaum tempatan', callback_data='prompt_model_ethnicity:random_malaysia')],
    ])


def prompt_model_age_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Kanak-kanak 4–7', callback_data='prompt_model_age:4-7')],
        [InlineKeyboardButton('Kanak-kanak 8–12', callback_data='prompt_model_age:8-12')],
        [InlineKeyboardButton('Remaja 13–17', callback_data='prompt_model_age:13-17')],
        [InlineKeyboardButton('Dewasa 18–25', callback_data='prompt_model_age:18-25')],
        [InlineKeyboardButton('Dewasa 26–40', callback_data='prompt_model_age:26-40')],
        [InlineKeyboardButton('Dewasa 41–60', callback_data='prompt_model_age:41-60')],
        [InlineKeyboardButton('Dewasa 60+', callback_data='prompt_model_age:60+')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_text_presence_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📝 Ada teks', callback_data='prompt_text_presence:yes')],
        [InlineKeyboardButton('🚫 Tiada teks', callback_data='prompt_text_presence:no')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_text_mode_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Auto — Klippo pilih teks sesuai', callback_data='prompt_text_mode:auto')],
        [InlineKeyboardButton('✍️ Manual — Saya masukkan teks', callback_data='prompt_text_mode:manual')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_audio_presence_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔊 Ada suara', callback_data='prompt_audio_presence:yes')],
        [InlineKeyboardButton('🔇 Tiada suara', callback_data='prompt_audio_presence:no')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_speaker_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🗣️ Model AI bercakap sendiri', callback_data='prompt_speaker:model')],
        [InlineKeyboardButton('🎙️ Suara promoter di latar', callback_data='prompt_speaker:voiceover')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_language_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🇲🇾 Bahasa Melayu', callback_data='prompt_language:Malay'),
         InlineKeyboardButton('🇬🇧 English', callback_data='prompt_language:English')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_voiceover_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Auto — Klippo pilih suara sesuai', callback_data='prompt_voiceover:auto')],
        [InlineKeyboardButton('🎙️ Suara natural / santai', callback_data='prompt_voiceover:ai')],
        [InlineKeyboardButton('🥰 Suara comel / ceria', callback_data='prompt_voiceover:cute')],
        [InlineKeyboardButton('🧑‍💼 Suara serius / profesional', callback_data='prompt_voiceover:serious')],
        [InlineKeyboardButton('⚡ Suara bertenaga / teruja', callback_data='prompt_voiceover:energetic')],
        [InlineKeyboardButton('🤝 Suara mesra / bersahaja', callback_data='prompt_voiceover:friendly')],
        [InlineKeyboardButton('🎧 Suara lembut / tenang', callback_data='prompt_voiceover:soft')],
        [InlineKeyboardButton('✍️ Saya masukkan skrip sendiri', callback_data='prompt_voiceover:script')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def _prompt_is_child_product(user_data):
    """Conservative age-fit check based on the selected product category/subcategory."""
    category = str(user_data.get('prompt_product_type', '')).lower()
    subcategory = str(user_data.get('prompt_product_subcategory', '')).lower()
    name = ' '.join(str(user_data.get(key, '') or '') for key in (
        'prompt_product_name', 'prompt_library_details',
        'prompt_custom_category_name', 'prompt_custom_subcategory_name'
    )).lower()
    child_subcategories = {
        'fashion_kids', 'shoes_kids', 'baby_clothing', 'baby_feeding',
        'baby_bath', 'baby_toy', 'baby_gear', 'baby_sleep', 'baby_other',
        'toy_educational', 'toy_figure', 'toy_building', 'toy_outdoor',
        'toy_baby', 'toy_game', 'toy_other', 'stationery_school'
    }
    child_words = (
        'kanak-kanak', 'kanak kanak', 'budak', 'bayi', 'kanak', 'kids',
        'children', 'child', 'toddler', 'baby', 'newborn', 'infant',
        'kidswear', 'junior', 'school uniform', 'baju sekolah',
        'school bag', 'schoolbag', 'school shoes', 'kasut sekolah',
        'children wear', 'children’s wear', 'childrens wear',
    )
    return (
        subcategory in child_subcategories
        or category in {'baby', 'toy'}
        or any(word in name for word in child_words)
    )


def prompt_creative_settings(user_data, include_audio=True):
    """Return short English instructions based only on the user's selected options."""
    age = str(user_data.get('prompt_model_age', '26-40'))
    child_model = age in {'4-7', '8-12', '13-17'}
    child_product = _prompt_is_child_product(user_data)
    category = str(user_data.get('prompt_product_type', '')).casefold()
    subcategory = str(user_data.get('prompt_product_subcategory', '')).casefold()
    baby_product = category == 'baby' or subcategory.startswith('baby_')
    if user_data.get('prompt_framing') == 'product_only':
        model = 'Model: none; no human or animal, hands, face or body parts; focus entirely on the exact product.'
    elif user_data.get('prompt_model_presence') == 'animal':
        species = str(user_data.get('prompt_animal_species', 'auto'))
        species_labels = {
            'auto': 'an animal species that clearly matches the named product; infer conservatively, otherwise use a cat or dog only when context supports it',
            'cat': 'one cat',
            'dog': 'one dog',
            'rabbit': 'one rabbit',
            'bird': 'one bird',
            'hamster': 'one hamster',
            'fish': 'one fish',
            'horse': 'one horse',
        }
        model = 'Model: ' + species_labels.get(species, species_labels['auto']) + '; natural, calm, species-appropriate behaviour; show the animal interacting with or naturally using the product only when safe and plausible. Never force tricks, unsafe handling, distress, or unsupported product claims.'
    elif user_data.get('prompt_model_presence') == 'yes':
        count = min(2, max(1, int(user_data.get('prompt_model_count', 1) or 1)))
        gender = user_data.get('prompt_model_gender', 'female')
        gender_label = {'female': 'female', 'male': 'male', 'auto': 'matching the product/reference; if unclear, use neutral natural styling'}.get(gender, 'matching the product/reference')
        appearance_key = user_data.get('prompt_model_ethnicity', 'random_malaysia')
        appearance = {
            'Malay': 'Malay Malaysian',
            'Chinese': 'Chinese Malaysian',
            'Indian': 'Indian Malaysian',
            'random_malaysia': 'one randomly selected Malaysian ethnicity',
            'Asian': 'Asian',
            'diverse': 'diverse appearance',
            'any': 'any appearance',
        }.get(appearance_key, 'one randomly selected Malaysian ethnicity')
        if baby_product and child_model:
            model = 'Model: no child or teen; use adult caregiver hands if needed or show the baby product alone. Keep all handling supervised and age-appropriate.'
        elif baby_product:
            model = f'Model: {count} adult caregiver model(s), gender presentation {gender_label}, {appearance}, age {age}; demonstrate only safe, supervised use and keep the baby product clearly visible.'
        elif child_model and not child_product:
            model = 'Model: no child or teen; focus on the product and use adult hands if needed.'
        elif child_model:
            model = f'Model: {count} child/teen model(s), age {age}, gender presentation {gender_label}, {appearance}; match the product/reference, keep identity consistent and actions age-appropriate.'
        elif child_product:
            model = f'Model: {count} adult model(s), gender presentation {gender_label}, {appearance}, age {age}; show child-sized products on a suitable surface, hanger or mannequin.'
        else:
            model = f'Model: {count} adult model(s), gender presentation {gender_label}, {appearance}, age {age}; keep identity and outfit consistent.'
    else:
        model = 'Model: none; focus on the product.'

    # The single-model video prompt must retain the explicit hijab choice too.
    if (
        user_data.get('prompt_model_presence') == 'yes'
        and user_data.get('prompt_framing') != 'product_only'
        and int(user_data.get('prompt_model_count', 1) or 1) == 1
        and user_data.get('prompt_model_gender') == 'female'
        and not model.startswith('Model: no child or teen')
    ):
        hijab_choice = user_data.get('prompt_model_hijab', 'na')
        if hijab_choice == 'hijab':
            model += ' Head covering: the female model wears a hijab; keep its style and placement consistent.'
        elif hijab_choice == 'no_hijab':
            model += ' Head covering: no hijab; keep the model hair visible and do not add a head covering.'

    # build_prompt() already supplies format, product lock and continuity.
    # Keep this helper focused on the user's selected model, audio and text options.
    lines = [model]
    angle_instruction = creative_angle_instruction(user_data.get('prompt_ad_angle', 'auto'))
    if angle_instruction:
        lines.append(angle_instruction)
    if include_audio:
        language = user_data.get('prompt_language', 'Malay')
        voiceover_mode = user_data.get('prompt_voiceover_mode', 'none')
        if voiceover_mode == 'ai':
            voice_styles = {
                'ai': 'natural and relaxed', 'cute': 'cute and cheerful',
                'serious': 'calm and confident', 'energetic': 'energetic, not shouty',
                'friendly': 'friendly and approachable', 'soft': 'gentle and clear',
                'custom': 'natural',
            }
            voice_style = voice_styles.get(user_data.get('prompt_voiceover_style', 'ai'), 'natural and relaxed')
            lang = 'Bahasa Melayu Malaysia' if language != 'English' else 'English'
            speaker = user_data.get('prompt_speech_source', 'voiceover')
            source = 'The on-camera model speaks' if speaker == 'model' else 'Use an off-camera promoter voice'
            copy_direction = spoken_copy_direction(language)
            lines.append(f'{source} in {lang}, {voice_style} style. {copy_direction} Keep dialogue short and background music below the voice.')
        elif voiceover_mode == 'script':
            script = ' '.join((user_data.get('prompt_voiceover_script') or '').split())
            lines.append('Use this exact spoken script: ' + script)
        else:
            lines.append('No spoken dialogue.')
    if user_data.get('prompt_on_screen_text') == 'yes':
        if user_data.get('prompt_text_mode') == 'manual' and user_data.get('prompt_text_content'):
            lines.append('On-screen text, exactly as supplied: ' + str(user_data['prompt_text_content']))
        else:
            text_language = 'English' if user_data.get('prompt_language') == 'English' else 'Bahasa Melayu Malaysia'
            lines.append(
                f'ON-SCREEN COPY ({text_language}): Create at most two short overlays: a distinctive product-specific hook near the opening and a clear, varied CTA at the end. '
                'Make the wording match the actual product and storyboard; do not repeat generic phrases such as “Kenali produk ini”. '
                'Use only supplied or verified product details. Never invent prices, discounts, stock urgency, popularity, specifications or results. '
                'Keep spelling exact, readable and uncluttered; do not duplicate the voice-over word for word.'
            )
    elif user_data.get('prompt_on_screen_text') == 'no':
        lines.append('No on-screen text.')
    if user_data.get('prompt_custom_background'):
        lines.append('Use the separately uploaded background image as the scene and match its perspective and lighting.')
    return '\n'.join(lines)


PRODUCT_SUBTYPES = {
    'fashion': [('fashion_women', '👗 Pakaian wanita'), ('fashion_men', '👔 Pakaian lelaki'), ('fashion_dress', '✨ Dress / Jubah'), ('fashion_sport', '🏃 Pakaian sukan'), ('fashion_outerwear', '🧥 Jaket / Outerwear'), ('fashion_kids', '🧒 Pakaian kanak-kanak'), ('fashion_innerwear', '🩱 Pakaian dalam'), ('fashion_other', '📦 Fesyen lain')],
    'bag': [('bag_handbag', '👜 Beg tangan'), ('bag_sling', '🎒 Beg silang / Sling'), ('bag_backpack', '🎒 Beg galas / Sekolah'), ('bag_laptop', '💻 Beg laptop'), ('bag_travel', '🧳 Beg perjalanan'), ('bag_wallet', '👛 Dompet / Card holder'), ('bag_tote', '🛍️ Tote bag'), ('bag_other', '📦 Beg lain')],
    'hijab': [('hijab_bawal', '🧕 Tudung bawal'), ('hijab_shawl', '🧣 Shawl'), ('hijab_instant', '🧕 Tudung sarung / Instant'), ('hijab_sport', '🏃 Tudung sukan'), ('hijab_inner', '🧢 Anak tudung'), ('hijab_accessory', '✨ Aksesori tudung'), ('hijab_other', '📦 Tudung lain')],
    'shoes': [('shoes_sneakers', '👟 Sneakers / Kasut sukan'), ('shoes_formal', '👞 Kasut formal'), ('shoes_heels', '👠 Kasut tumit'), ('shoes_sandals', '🩴 Sandal / Selipar'), ('shoes_running', '🏃 Kasut larian'), ('shoes_kids', '🧒 Kasut kanak-kanak'), ('shoes_other', '📦 Kasut lain')],
    'beauty': [('beauty_skincare', '🧴 Skincare'), ('beauty_makeup', '💄 Makeup'), ('beauty_hair', '💇 Penjagaan rambut'), ('beauty_perfume', '🌸 Perfume / Wangian'), ('beauty_body', '🧼 Penjagaan badan'), ('beauty_tools', '🪞 Alat kecantikan'), ('beauty_other', '📦 Kecantikan lain')],
    'food': [('food_snacks', '🍪 Snek / Kerepek'), ('food_drinks', '🥤 Minuman'), ('food_supplements', '🥣 Makanan tambahan'), ('food_frozen', '🧊 Makanan sejuk beku'), ('food_cooking', '🍳 Bahan masakan / Sos'), ('food_bakery', '🍰 Biskut / Bakeri'), ('food_other', '📦 Makanan lain')],
    'gadget': [('gadget_phone', '📱 Telefon / Aksesori telefon'), ('gadget_audio', '🎧 Audio / Earbuds'), ('gadget_computer', '💻 Komputer / Aksesori'), ('gadget_smart', '⌚ Jam pintar / Wearable'), ('gadget_camera', '📷 Kamera / Aksesori'), ('gadget_home', '🔌 Elektronik rumah'), ('gadget_other', '📦 Gajet lain')],
    'home': [('home_kitchen', '🍳 Dapur / Peralatan memasak'), ('home_storage', '🗄️ Penyimpanan / Organizer'), ('home_cleaning', '🧹 Pembersihan'), ('home_decor', '🪴 Dekorasi rumah'), ('home_bedding', '🛏️ Cadar / Peralatan tidur'), ('home_lighting', '💡 Lampu'), ('home_furniture', '🪑 Perabot'), ('home_other', '📦 Rumah lain')],
    'accessory': [('accessory_watch', '⌚ Jam tangan'), ('accessory_jewelry', '💍 Barang kemas'), ('accessory_eyewear', '🕶️ Cermin mata'), ('accessory_belt', '🪢 Tali pinggang'), ('accessory_hair', '🎀 Aksesori rambut'), ('accessory_scarf', '🧣 Skaf / Aksesori fesyen'), ('accessory_other', '📦 Aksesori lain')],
    'toy': [('toy_educational', '🧩 Mainan pendidikan'), ('toy_figure', '🧸 Patung / Figure'), ('toy_building', '🧱 Blok binaan'), ('toy_outdoor', '🪁 Mainan luar'), ('toy_baby', '🪇 Mainan bayi'), ('toy_game', '🎲 Permainan / Board game'), ('toy_other', '📦 Mainan lain')],
    'book_stationery': [('stationery_books', '📚 Buku'), ('stationery_pen', '🖊️ Pen / Pensel'), ('stationery_notebook', '📓 Buku nota / Planner'), ('stationery_art', '🎨 Alat seni'), ('stationery_school', '🎒 Alat tulis sekolah'), ('stationery_office', '📎 Fail / Alat pejabat'), ('stationery_other', '📦 Buku / alat tulis lain')],
    'sports': [('sports_fitness', '🏋️ Kecergasan / Gym'), ('sports_running', '🏃 Larian'), ('sports_ball', '⚽ Sukan bola'), ('sports_racket', '🏸 Raket / Badminton'), ('sports_cycling', '🚴 Berbasikal'), ('sports_outdoor', '⛺ Aktiviti luar'), ('sports_bottle', '🥤 Botol sukan'), ('sports_other', '📦 Sukan lain')],
    'pet': [('pet_food', '🦴 Makanan haiwan'), ('pet_grooming', '🧴 Penjagaan / Grooming'), ('pet_toy', '🧸 Mainan haiwan'), ('pet_bed', '🛏️ Katil / Tempat rehat'), ('pet_accessory', '🐕 Tali / Aksesori'), ('pet_cleaning', '🧹 Kebersihan haiwan'), ('pet_other', '📦 Produk haiwan lain')],
    'automotive': [('auto_car', '🚗 Aksesori kereta'), ('auto_motorcycle', '🏍️ Aksesori motosikal'), ('auto_care', '🧽 Penjagaan / Pembersihan'), ('auto_electronic', '📱 Elektronik kenderaan'), ('auto_interior', '🪑 Aksesori dalaman'), ('auto_exterior', '✨ Aksesori luaran'), ('auto_other', '📦 Automotif lain')],
    'baby': [('baby_clothing', '👶 Pakaian bayi'), ('baby_feeding', '🍼 Penyusuan / Makan'), ('baby_bath', '🛁 Mandian / Penjagaan'), ('baby_toy', '🧸 Mainan bayi'), ('baby_gear', '🚼 Stroller / Kelengkapan'), ('baby_sleep', '🌙 Tidur / Keselamatan'), ('baby_other', '📦 Produk bayi lain')],
    'travel': [('travel_luggage', '🧳 Bagasi / Beg travel'), ('travel_organizer', '🧩 Organizer perjalanan'), ('travel_pillow', '💤 Bantal perjalanan'), ('travel_accessory', '🛂 Aksesori perjalanan'), ('travel_toiletry', '🧴 Beg toiletries'), ('travel_outdoor', '🏕️ Kelengkapan kembara'), ('travel_other', '📦 Kembara lain')],
    'office': [('office_desk', '🖇️ Alat meja pejabat'), ('office_storage', '🗄️ Fail / Penyimpanan'), ('office_electronics', '🖨️ Elektronik pejabat'), ('office_furniture', '🪑 Perabot pejabat'), ('office_stationery', '✏️ Alat tulis pejabat'), ('office_cleaning', '🧹 Kebersihan ruang kerja'), ('office_other', '📦 Pejabat lain')],
    'other': [('other_health', '🧴 Kesihatan / Penjagaan diri'), ('other_garden', '🌱 Taman / Berkebun'), ('other_hobby', '🎨 Hobi / Kraf'), ('other_car', '🚗 Aksesori kenderaan'), ('other_daily', '🏠 Keperluan harian'), ('other_gift', '🎁 Hadiah'), ('other_other', '📦 Lain-lain')],
}

PRODUCT_SUBTYPE_LABELS = {
    slug: label for options in PRODUCT_SUBTYPES.values() for slug, label in options
}

def prompt_product_type_menu():
    items = list(PRODUCT_TYPES.items())
    rows = []
    for index in range(0, len(items), 2):
        pair = items[index:index + 2]
        rows.append([InlineKeyboardButton(label, callback_data='prompt_product_type:' + key) for key, label in pair])
    rows.append([InlineKeyboardButton('↩️ Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def prompt_product_subtype_menu(category: str):
    options = PRODUCT_SUBTYPES.get(category, [('other_other', '📦 Lain-lain')])
    rows = []
    for index in range(0, len(options), 2):
        pair = options[index:index + 2]
        rows.append([InlineKeyboardButton(label, callback_data='prompt_product_subcategory:' + slug) for slug, label in pair])
    rows.append([InlineKeyboardButton('↩️ Tukar Kategori', callback_data='prompt_product_categories')])
    rows.append([InlineKeyboardButton('🏠 Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def prompt_setup_mode_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Auto — Klippo pilih tetapan sesuai', callback_data='prompt_setup:auto')],
        [InlineKeyboardButton('🎛️ Manual — Saya pilih sendiri', callback_data='prompt_setup:manual')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_duration_menu():
    # Keep all five established duration/segmentation choices distinct.
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎬 10 saat', callback_data='prompt_duration:10')],
        [InlineKeyboardButton('🎞️ 20 saat', callback_data='prompt_duration:20_single')],
        [InlineKeyboardButton('🎞️ 20 saat (10 + 10)', callback_data='prompt_duration:20_split')],
        [InlineKeyboardButton('🎬 30 saat', callback_data='prompt_duration:30_single')],
        [InlineKeyboardButton('🎬 30 saat (10 + 10 + 10)', callback_data='prompt_duration:30_split')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


def prompt_ad_angle_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Auto — ikut produk', callback_data='prompt_ad_angle:auto')],
        [InlineKeyboardButton('❓ Hook berbentuk soalan', callback_data='prompt_ad_angle:question')],
        [InlineKeyboardButton('✨ Reveal produk yang menarik', callback_data='prompt_ad_angle:reveal')],
        [InlineKeyboardButton('🖐️ Demonstrasi ringkas', callback_data='prompt_ad_angle:demo')],
        [InlineKeyboardButton('🏡 Situasi harian / relatable', callback_data='prompt_ad_angle:relatable')],
        [InlineKeyboardButton('💎 Premium / editorial', callback_data='prompt_ad_angle:premium')],
        [InlineKeyboardButton('🛍️ Promoter affiliate bertenaga', callback_data='prompt_ad_angle:affiliate')],
        [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
    ])


# Keep the style picker relevant to the selected product instead of showing
# unrelated options (for example, Mirror Selfie for a food product).
PRODUCT_STYLE_KEYS = {
    'fashion': {'fashion_editorial', 'golden_hour', 'mirror_selfie', 'lifestyle', 'ugc_review', 'creative_reveal', 'studio_360_safe', 'minimal', 'luxury', 'white_doodle'},
    'bag': {'handbag_showcase', 'bag_detail_macro', 'bag_flatlay', 'bag_daily_carry', 'bag_tabletop_reveal', 'sling_bag_lifestyle', 'backpack_demo', 'white_doodle', 'minimal', 'luxury', 'studio_360_safe', 'lifestyle', 'unboxing'},
    'wallet': {'wallet_luxury_macro', 'wallet_open_close', 'wallet_daily_carry', 'wallet_flatlay', 'wallet_gift_reveal', 'white_doodle', 'minimal', 'luxury', 'studio_360_safe'},
    'hijab': {'fashion_editorial', 'golden_hour', 'lifestyle', 'ugc_review', 'creative_reveal', 'white_doodle', 'minimal', 'luxury'},
    'shoes': {'studio_360_safe', 'pov_demo', 'lifestyle', 'ugc_review', 'creative_reveal', 'fast_cut', 'white_doodle', 'minimal'},
    'beauty': {'beauty_macro', 'ugc_review', 'luxury', 'minimal', 'creative_reveal', 'flatlay', 'unboxing', 'white_doodle'},
    'food': {'food_appetite', 'nature_fresh', 'flatlay', 'lifestyle', 'creative_reveal', 'playful_viral', 'white_doodle', 'minimal'},
    'gadget': {'tech_demo', 'studio_360_safe', 'unboxing', 'minimal', 'creative_reveal', 'flatlay', 'white_doodle'},
    'equipment': {'tech_demo', 'pov_demo', 'studio_360_safe', 'unboxing', 'minimal', 'lifestyle', 'creative_reveal', 'white_doodle'},
    'home': {'cozy_home', 'pov_demo', 'flatlay', 'lifestyle', 'creative_reveal', 'unboxing', 'minimal', 'white_doodle'},
    'accessory': {'luxury', 'flatlay', 'studio_360_safe', 'creative_reveal', 'minimal', 'unboxing', 'white_doodle'},
    'toy': {'playful_viral', 'funny_ad', 'pov_demo', 'unboxing', 'creative_reveal', 'studio_360_safe', 'minimal', 'white_doodle'},
    'book_stationery': {'flatlay', 'minimal', 'lifestyle', 'creative_reveal', 'fast_cut', 'unboxing', 'white_doodle'},
    'sports': {'dynamic', 'pov_demo', 'fast_cut', 'lifestyle', 'studio_360_safe', 'ugc_review', 'minimal', 'white_doodle'},
    'pet': {'lifestyle', 'pov_demo', 'playful_viral', 'studio_360_safe', 'minimal', 'white_doodle'},
    'automotive': {'tech_demo', 'studio_360_safe', 'pov_demo', 'minimal', 'creative_reveal', 'white_doodle'},
    'baby': {'cozy_home', 'lifestyle', 'flatlay', 'minimal', 'unboxing', 'white_doodle'},
    'travel': {'studio_360_safe', 'lifestyle', 'flatlay', 'unboxing', 'minimal', 'white_doodle'},
    'office': {'flatlay', 'minimal', 'lifestyle', 'creative_reveal', 'unboxing', 'white_doodle'},
    'other': {'cinematic', 'minimal', 'lifestyle', 'flatlay', 'unboxing', 'creative_reveal', 'studio_360_safe', 'white_doodle'},
}
# Camera framing is separate from the visual aesthetic (Luxury, Cinematic, White Doodle, etc.).
# Keep these choices short and filter them to the selected product category.
PRODUCT_FRAMING = {
    'auto': ('🎲 Automatik — Klippo pilih', 'Ikut jenis produk; pilih framing dan aksi paling sesuai.'),
    'detail': ('🔎 Fokus produk sahaja', 'Use close or medium-close framing so the product and its important real details dominate the frame. Keep only the relevant body area in view when worn; do not force a face or full body into the shot.'),
    'model': ('🧍 Model memperagakan', 'Use a natural external-camera shot of the model demonstrating the product. Keep the product clearly visible and use believable movements; the model must not hold a phone or film themselves.'),
    'pov': ('👀 POV — sudut pandangan sendiri', 'Use a believable first-person point of view, showing hands and the product as a real viewer would see them. Avoid showing an impossible camera operator or unnecessary face/full body.'),
    'demo': ('🖐️ Tunjuk cara penggunaan', 'Show a short, clear, physically plausible product-use demonstration with hands and relevant details in frame. Do not invent product features.'),
    'lifestyle': ('🏡 Gaya kehidupan harian', 'Show the product naturally in a believable everyday situation that suits the selected location; the product must remain easy to see.'),
    'product_only': ('📦 Produk sahaja — tanpa model', 'Show the product alone with a clean, realistic product-focused composition; no person, hands, face, or body parts.'),
    'shoes_feet': ('👟 Kasut dipakai — fokus kaki', 'Frame low on the worn shoes and lower legs. Keep shoes as the clear hero; face and full body are unnecessary. Show natural foot placement and realistic contact with the ground.'),
    'shoes_walk': ('🚶 Kasut ketika berjalan', 'Show a few natural steps with the camera tracking the shoes and lower legs. Preserve realistic foot contact, weight transfer, and the exact shoe design; no exaggerated lifting or robotic marching.'),
    'shoes_car': ('🚗 Kasut ketika duduk dalam kereta', 'The model is seated in a stationary, parked car. Frame downward on the worn shoes and lower legs only; keep the face and full body out of frame. Show a small natural foot repositioning. The vehicle must remain stationary. No phone, mirror selfie, or filming by the model.'),
    'hijab_detail': ('🧕 Fokus gaya & lipatan tudung', 'Use a medium-close frame around the head, shoulders, and upper torso to show the actual hijab drape, folds, fabric texture, and styling. Preserve the real colour and design.'),
    'beauty_apply': ('💄 Produk & cara aplikasi', 'Frame the product and the relevant hand/application area. Show a gentle, plausible application only when suitable for the product; do not invent effects or claim results.'),

    'fabric_detail': ('🧵 Close-up tekstur fabrik', 'Show actual fabric, stitching, seams, and visible finish in a controlled close-up. Do not invent patterns or labels.'),
    'outfit_walk': ('👗 Pakaian ketika berjalan', 'Show a few natural steps and a subtle turn that reveals garment drape. Use an external camera; no phone or mirror-selfie behaviour.'),
    'seated_style': ('🪑 Gaya santai ketika duduk', 'Show the outfit naturally while seated with a small comfortable adjustment. Keep garment details visible and anatomy natural.'),
    'hijab_walk': ('🧕 Tudung ketika bergerak', 'Show a short natural walk or gentle turn so the hijab drape is visible. Preserve exact colour, folds, and styling.'),
    'hijab_fabric': ('🪡 Kain & kemasan tudung', 'Use a close-up of actual fabric texture, edge finishing, and folds. Do not invent embroidery or unseen details.'),
    'shoes_material': ('🧵 Bahan & jahitan kasut', 'Show the actual upper, stitching, fastening, and visible sole edge. Do not invent tread or hidden outsole details.'),
    'shoes_pair': ('👟 Paparan sepasang kasut', 'Show both shoes together, then a slow side reveal. Preserve proportions, colour, and construction; no floating or morphing.'),
    'bag_wear': ('👜 Beg dipakai pada badan', 'Show the bag worn in its intended way—shoulder, crossbody, or backpack. Keep the bag clear and do not alter straps or hardware.'),
    'bag_open': ('👜 Buka beg & tunjuk ruang', 'Show hands opening the bag and reveal only visible, plausible compartments. Do not invent pockets or capacity.'),
    'bag_table': ('🪑 Beg di atas meja', 'Keep the bag on a stable surface while the camera reveals silhouette, handles, straps, and visible hardware. No shape changes.'),
    'wallet_open': ('👛 Buka dompet & tunjuk ruang', 'Show hands opening the wallet and reveal only visible compartments. Do not add unsupported features or accessories.'),
    'wallet_cards': ('💳 Kad dan ruang simpanan', 'Show one plain card placed into a slot only if that slot is genuinely present. Keep wallet structure realistic.'),
    'wallet_pocket': ('👖 Dompet masuk poket', 'Show a natural hand placing the wallet into a suitable pocket or taking it out. Preserve its real thickness and proportions.'),
    'beauty_texture': ('✨ Close-up tekstur produk', 'Show a small realistic amount or swatch only when appropriate. Preserve true colour; no magical transformation or unsupported skin results.'),
    'beauty_unbox': ('📦 Buka pembungkusan produk', 'Show hands opening the actual packaging. Do not invent extra items, seals, or accessories.'),
    'food_texture': ('🍓 Close-up tekstur makanan', 'Show realistic food texture and surface with natural light. Do not add ingredients, toppings, steam, or fillings that are not shown.'),
    'food_serve': ('🍽️ Hidang atau tuang makanan', 'Show one plausible serving action when suitable. Keep portions and ingredients consistent and avoid impossible food physics.'),
    'food_hand': ('🥡 Produk di tangan', 'Show a hand holding the actual food or package naturally. Keep packaging and food appearance unchanged.'),
    'gadget_hand': ('📱 Gajet digunakan dengan tangan', 'Show one simple action the actual device supports. Keep buttons, ports, shape, and screen layout consistent.'),
    'gadget_screen': ('🔍 Fokus skrin & kawalan', 'Use a steady close-up of the real screen and controls. Avoid fabricated UI, gibberish text, extra buttons, or screen distortion.'),
    'gadget_ports': ('🔌 Fokus port & sambungan', 'Show only ports, connectors, and accessories actually present. Do not add compatibility claims or extra cables.'),
    'equipment_use': ('🖐️ Tunjuk cara guna peralatan', 'Demonstrate one simple, normal use of the actual product from start to finish. Show the real hand placement, controls, and product response clearly. Keep the device stable and physically plausible; do not invent features or results.'),
    'equipment_controls': ('🎛️ Butang & kawalan', 'Use a close, steady shot of the actual switch, dial, button, or control being operated once. Show only controls that are visible on the product and a believable response; do not add lights, displays, sounds, or functions that are not supported by the reference.'),
    'equipment_setup': ('🧰 Persediaan sebelum digunakan', 'Show a simple, plausible setup using only the supplied product and visible accessories. Keep cable connections and component placement realistic; do not invent tools, parts, or installation steps.'),
    'equipment_working': ('⚙️ Produk sedang berfungsi', 'Show the product performing its ordinary intended task in a realistic setting. Keep the working area and product response visible, with no exaggerated effects, fake performance claims, or impossible motion.'),
    'home_in_use': ('🏠 Produk dalam penggunaan sebenar', 'Show one believable everyday task. Preserve realistic scale and operation; do not imply results beyond what is visible.'),
    'home_setup': ('🛠️ Pasang atau sediakan produk', 'Show a plausible setup step only when suitable. Do not invent tools, components, or installation steps.'),
    'home_scale': ('📏 Tunjuk saiz produk', 'Frame the product beside an ordinary hand or familiar object for natural scale without distorting perspective or claiming exact measurements.'),
    'accessory_wear': ('💍 Aksesori ketika dipakai', 'Frame only the relevant body area wearing the accessory. Preserve its true shape, size, colour, and placement.'),
    'accessory_close': ('💎 Close-up kemasan aksesori', 'Show visible material, clasp, setting, and finish. Do not invent gemstones, metal type, engravings, or hidden details.'),
    'toy_play': ('🧸 Mainan sedang digunakan', 'Show a simple, safe interaction that matches the actual toy. Keep its design stable and do not add pieces or functions.'),
    'toy_feature': ('🧩 Tunjuk bahagian utama mainan', 'Reveal actual parts and movement only if supported by the design. No extra pieces or impossible motion.'),
    'stationery_write': ('✍️ Tulis atau guna alat tulis', 'Show a hand using the actual stationery on a suitable surface. Keep the item stable and avoid invented legible text.'),
    'stationery_flatlay': ('📚 Susunan alat tulis dari atas', 'Use a clean top-down view of the actual stationery on a stable surface. Do not add extra products or labels.'),
    'sports_action': ('🏃 Produk dalam aksi sukan', 'Show restrained, realistic movement suited to the product. Prioritise safe handling and keep the product visible.'),
    'sports_grip': ('✋ Fokus genggaman & bahan', 'Show the hand holding or gripping the product as intended. Preserve real grip points, surface texture, and proportions.'),
    'pet_interact': ('🐾 Interaksi dengan haiwan', 'Show a calm, safe interaction only when suitable. Keep the product visible and do not force animal behaviour or unsafe use.'),
    'auto_install': ('🔧 Tunjuk pemasangan ringkas', 'Show plausible, safe placement only if the product supports it. Keep the vehicle stationary; do not invent tools or compatibility.'),
    'auto_detail': ('🚘 Butiran aksesori kereta', 'Show the actual automotive product in its real position. Preserve mounting, scale, and connectors; vehicle remains stationary.'),
    'baby_safe_use': ('🍼 Fokus penggunaan selamat', 'Show a calm, supervised, age-appropriate setting. Avoid unsafe handling and do not imply certifications not provided.'),
    'kids_cute': ('🥰 Aksi comel & ceria kanak-kanak', 'Create a lively, charming Malaysian kids-ad moment: start with a curious glance at the product, then a genuine delighted smile and one playful, age-appropriate action that suits the item (e.g. a tiny happy bounce in place, a cheerful twirl to show an outfit, proudly presenting the item, or a playful peek-and-reveal). Finish with a warm natural reaction toward the camera. Pick the best action for this exact product; vary it between generations, keep the product clearly visible, movements realistic, and styling modest and age-appropriate. No adult-like posing, risky stunts, exaggerated expressions, or product changes. The child should look Malaysian, not foreign-stereotyped.'),
    'baby_gentle': ('👶 Gaya lembut produk bayi', 'Use a calm, tender baby-product presentation. Prefer a caregiver’s gentle hands, a clean nursery, a child-sized hanger/mannequin, or a stable product display as appropriate to the exact item. If a baby is visible in the reference, keep handling safe and fully supported; never place a baby on an elevated or unstable surface, near small detachable parts, or in an unsafe sleep setup. Do not invent product features or imply safety certification.'),
    'travel_pack': ('🧳 Susun barang perjalanan', 'Show realistic packing with plausible items. Preserve bag dimensions and compartments; do not overstate capacity.'),
    'office_work': ('🖇️ Produk ketika bekerja', 'Show the product naturally used at a desk. Avoid fabricated documents, interface text, or unsupported functions.'),
}
PRODUCT_FRAMING_KEYS = {
    'fashion': ('fabric_detail','outfit_walk','seated_style','detail','model','lifestyle','product_only'),
    'hijab': ('hijab_detail','hijab_walk','hijab_fabric','model','lifestyle','product_only'),
    'shoes': ('shoes_feet','shoes_walk','shoes_car','shoes_material','shoes_pair','detail','product_only'),
    'bag': ('bag_wear','bag_open','bag_table','detail','model','demo','lifestyle','product_only'),
    'wallet': ('wallet_open','wallet_cards','wallet_pocket','detail','demo','pov','lifestyle','product_only'),
    'beauty': ('beauty_apply','beauty_texture','beauty_unbox','detail','demo','lifestyle','product_only'),
    'food': ('food_texture','food_serve','food_hand','detail','pov','lifestyle','product_only'),
    'gadget': ('gadget_hand','gadget_screen','gadget_ports','equipment_use','equipment_controls','equipment_working','detail','pov','demo','lifestyle','product_only'),
    'equipment': ('equipment_use','equipment_controls','equipment_setup','equipment_working','home_scale','detail','pov','demo','lifestyle','product_only'),
    'home': ('home_in_use','home_setup','home_scale','equipment_use','equipment_controls','equipment_setup','equipment_working','detail','pov','demo','lifestyle','product_only'),
    'accessory': ('accessory_wear','accessory_close','detail','model','demo','lifestyle','product_only'),
    'toy': ('toy_play','toy_feature','detail','pov','demo','lifestyle','product_only'),
    'book_stationery': ('stationery_write','stationery_flatlay','detail','pov','demo','lifestyle','product_only'),
    'sports': ('sports_action','sports_grip','detail','model','demo','lifestyle','product_only'),
    'pet': ('pet_interact','detail','pov','lifestyle','product_only'),
    'automotive': ('auto_install','auto_detail','detail','pov','demo','lifestyle','product_only'),
    'baby': ('baby_safe_use','detail','demo','lifestyle','product_only'),
    'travel': ('travel_pack','detail','model','demo','lifestyle','product_only'),
    'office': ('office_work','equipment_use','equipment_controls','equipment_working','detail','pov','demo','lifestyle','product_only'),
    'other': ('detail','model','pov','demo','lifestyle','product_only'),
}

def prompt_framing_menu(product_type='other', model_presence=None, user_data=None):
    user_data = user_data or {}
    keys = list(PRODUCT_FRAMING_KEYS.get(product_type, PRODUCT_FRAMING_KEYS['other']))
    # Offer age-specific actions only when the selected product and model fit.
    if _prompt_is_child_product(user_data):
        selected_age = str(user_data.get('prompt_model_age', '26-40'))
        if product_type == 'baby':
            keys.append('baby_gentle')
        elif model_presence == 'yes' and selected_age in {'4-7', '8-12', '13-17'}:
            keys.append('kids_cute')
    rows = [[InlineKeyboardButton(PRODUCT_FRAMING['auto'][0], callback_data='prompt_framing:auto')]]
    for key in keys:
        label = PRODUCT_FRAMING[key][0]
        if model_presence != 'yes' and key in ('model', 'hijab_detail', 'hijab_walk', 'hijab_fabric', 'shoes_feet', 'shoes_walk', 'shoes_car', 'beauty_apply', 'outfit_walk', 'seated_style', 'bag_wear', 'accessory_wear', 'pet_interact', 'baby_safe_use'):
            # Do not offer worn-on-body or application shots when the user chose no model.
            continue
        rows.append([InlineKeyboardButton(label, callback_data='prompt_framing:' + key)])
    rows.append([InlineKeyboardButton('↩️ Tukar Gaya Visual', callback_data='prompt_framing_back')])
    rows.append([InlineKeyboardButton('🏠 Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


CORE_USER_STYLE_KEYS = (
    'cinematic', 'minimal', 'lifestyle', 'dynamic',
    'luxury', 'flatlay', 'creative_reveal', 'white_doodle',
)
CORE_STYLE_LABELS = {
    'cinematic': '🎬 Realistic / Cinematic',
    'minimal': '✨ Minimalist Studio',
    'lifestyle': '🌿 Lifestyle Story',
    'dynamic': '⚡ Dynamic Action',
    'luxury': '💎 Luxury Commercial',
    'flatlay': '🧺 Clean Flat Lay',
    'creative_reveal': '✨ Creative Reveal',
    'white_doodle': '✏️ White Doodle',
}
CORE_STYLE_DESCRIPTIONS = {
    'cinematic': 'Visual realistik, pencahayaan sinematik dan gerakan kamera licin.',
    'minimal': 'Latar bersih, komposisi ringkas dan fokus penuh pada produk.',
    'lifestyle': 'Produk dalam situasi harian yang natural dan meyakinkan.',
    'dynamic': 'Aksi lebih bertenaga, pembukaan menarik dan potongan visual terkawal.',
    'luxury': 'Pencahayaan premium, tekstur jelas dan suasana elegan.',
    'flatlay': 'Paparan dari atas atau sudut tinggi dengan susunan kemas.',
    'creative_reveal': 'Pendedahan produk kreatif melalui cahaya, fokus dan pergerakan kamera.',
    'white_doodle': 'Garisan doodle putih animasi mengikut bentuk produk tanpa menutupinya.',
}


def prompt_style_guide(product_type='other'):
    available_keys = {key for key, _label in storyboard_styles()}
    return '\n'.join(
        '• ' + CORE_STYLE_LABELS[key] + ' — ' + CORE_STYLE_DESCRIPTIONS[key]
        for key in CORE_USER_STYLE_KEYS if key in available_keys
    )


# White Doodle is a universal overlay style and works across product categories.
# The legacy doodle_option = next category-filtering path is intentionally replaced by the compact universal style catalogue.
def prompt_style_menu(product_type='other', model_presence=None):
    """Show a compact, stable set of user-facing styles; vary execution automatically."""
    available = dict(storyboard_styles())
    rows = [
        [InlineKeyboardButton(CORE_STYLE_LABELS[key], callback_data='prompt_style:' + key)]
        for key in CORE_USER_STYLE_KEYS if key in available
    ]
    rows.append([InlineKeyboardButton('↩️ Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def prompt_category_menu():
    rows = []
    categories = PROMPT_LIBRARY.get('categories', [])
    for index in range(0, len(categories), 2):
        pair = categories[index:index + 2]
        rows.append([InlineKeyboardButton(f"{item.get('emoji', '🎬')} {item['label']}", callback_data=f"pcat:{item['id']}") for item in pair])
    rows.append([InlineKeyboardButton('↩️ Menu Utama', callback_data='home')])
    return InlineKeyboardMarkup(rows)


def prompt_options_menu(category_id: str, subtype: str = ''):
    category = CATEGORIES_BY_ID.get(category_id, {})
    rows = []
    prompt_ids = category.get('prompt_ids', [])
    if subtype:
        # Prefer exact subtype prompts plus category-wide concepts. Hide prompts for
        # unrelated subtypes (e.g. cleanser prompts when the title says lipstick).
        matching = [
            prompt_id for prompt_id in prompt_ids
            if (PROMPTS_BY_ID.get(prompt_id, {}).get('subtype') in ('', subtype)
                or 'subtype' not in PROMPTS_BY_ID.get(prompt_id, {}))
        ]
        if matching:
            prompt_ids = matching
    for prompt_id in prompt_ids:
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
        [InlineKeyboardButton('🌊 Navy Premium', callback_data='background:navy'),
         InlineKeyboardButton('🌿 Sage Natural', callback_data='background:sage')],
        [InlineKeyboardButton('🩵 Sky Blue', callback_data='background:sky'),
         InlineKeyboardButton('💜 Lavender', callback_data='background:lavender')],
        [InlineKeyboardButton('🌷 Rose', callback_data='background:rose'),
         InlineKeyboardButton('🍃 Mint', callback_data='background:mint')],
        [InlineKeyboardButton('🧱 Terracotta', callback_data='background:terracotta'),
         InlineKeyboardButton('🖤 Charcoal', callback_data='background:charcoal')],
        [InlineKeyboardButton('✨ Gradient Krim', callback_data='background:gradient'),
         InlineKeyboardButton('🌫️ Kelabu Lembut', callback_data='background:mist')],
        [InlineKeyboardButton('🩵 Gradient Sky', callback_data='background:sky_gradient'),
         InlineKeyboardButton('💜 Gradient Lavender', callback_data='background:lavender_gradient')],
        [InlineKeyboardButton('🌿 Gradient Sage', callback_data='background:sage_gradient'),
         InlineKeyboardButton('🌷 Gradient Blush', callback_data='background:blush_gradient')],
        [InlineKeyboardButton('🌌 Gradient Midnight', callback_data='background:midnight_gradient'),
         InlineKeyboardButton('🏖️ Gradient Sand', callback_data='background:sand_gradient')],
        [InlineKeyboardButton('◯ Corak Halus', callback_data='background:pattern'),
         InlineKeyboardButton('◐ Dua Tona', callback_data='background:duotone')],
        [InlineKeyboardButton('🌊 Ocean Blue', callback_data='background:ocean_gradient'),
         InlineKeyboardButton('🌲 Forest Green', callback_data='background:forest_gradient')],
        [InlineKeyboardButton('🌅 Sunset', callback_data='background:sunset_gradient'),
         InlineKeyboardButton('🌌 Aurora', callback_data='background:aurora_gradient')],
        [InlineKeyboardButton('☕ Mocha', callback_data='background:mocha_gradient'),
         InlineKeyboardButton('🍑 Peach', callback_data='background:peach_gradient')],
        [InlineKeyboardButton('🧊 Ice Blue', callback_data='background:ice_gradient'),
         InlineKeyboardButton('💚 Emerald', callback_data='background:emerald_gradient')],
        [InlineKeyboardButton('🍇 Plum', callback_data='background:plum_gradient'),
         InlineKeyboardButton('🪸 Coral', callback_data='background:coral_gradient')],
        [InlineKeyboardButton('🪨 Graphite', callback_data='background:graphite_gradient'),
         InlineKeyboardButton('🥂 Champagne', callback_data='background:champagne_gradient')],
        [InlineKeyboardButton('🍋 Lemon', callback_data='background:lemon_gradient'),
         InlineKeyboardButton('🩵 Teal', callback_data='background:teal_gradient')],
        [InlineKeyboardButton('💜 Lilac', callback_data='background:lilac_gradient'),
         InlineKeyboardButton('🔵 Cobalt', callback_data='background:cobalt_gradient')],
        [InlineKeyboardButton('🖼️ Guna Gambar Latar Sendiri', callback_data='background:custom')],
        [InlineKeyboardButton('↩️ Semak Gambar', callback_data='photos_order')],
    ])


def duration_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⏱️ 10 saat', callback_data='duration:10'),
         InlineKeyboardButton('⏱️ 15 saat', callback_data='duration:15')],
        [InlineKeyboardButton('⏱️ 20 saat', callback_data='duration:20')],
        [InlineKeyboardButton('↩️ Semak Gambar', callback_data='photos_order')],
    ])


def _contextual_motion_instruction(scene_key, product_type='other', model_presence='yes'):
    """Choose practical model action and camera framing from the selected location and product."""
    scene_actions = {
        'vanity': 'At the mirror or vanity, the model naturally checks the reflection, adjusts the item or outfit, and may turn once gently to inspect the side view. Use mirror-aware framing and a small smooth follow; avoid repeated spinning.',
        'airport': 'At the airport, the model walks naturally toward the terminal or seating area while carrying/wearing the product correctly. Track from the front or side at walking pace; keep arm swing, straps and product sway natural. Never stand rigidly and twirl a bag.',
        'mall': 'In the shopping mall, let the model walk at an easy pace, briefly pause near a storefront, or interact naturally with the product. Use a stable side-follow or front tracking view.',
        'boutique': 'In the boutique, the model may browse a rack, touch fabric lightly, or check the fit in a mirror. Frame the product clearly and follow the action smoothly.',
        'cafe': 'In the cafe, use a relaxed seated or standing interaction appropriate to the product, with a gentle push-in for product detail and a wider view to establish the setting.',
        'home': 'At home, use a believable everyday interaction that suits the product, with natural weight shifts and practical hand placement. Keep the camera at a comfortable eye-level or product-level angle.',
        'kitchen': 'In the kitchen, show one safe, practical use of the product on a counter or during food preparation when relevant. Keep hands and object contact believable; use a steady medium shot.',
        'living_room': 'In the living room, show a natural everyday interaction or a relaxed walk through the space if appropriate. Use a gentle follow or slow push-in.',
        'office': 'In the office, show the product being used naturally at a desk or while moving through the workspace. Use stable eye-level framing and a small push-in on the product.',
        'car_interior': 'Inside the car, keep the person seated and the product placed or used safely; do not show distracting movement while driving. Use a steady interior angle.',
        'bedroom': 'In the bedroom, use a relaxed, practical interaction that suits the product; if a mirror is present, the model may check the reflection and turn once naturally.',
        'garden': 'In the garden, allow a natural walk or simple product interaction with a gentle side-follow; keep the product readable.',
        'beach': 'At the beach, use a relaxed walk or practical interaction suited to the product, with a smooth side-follow or wide establishing view.',
        'gym': 'In the gym, show a safe, correct use of the product or equipment with stable framing; movement should match the activity.',
        'library': 'In the library, show quiet, believable interaction with the product. Use restrained camera movement and avoid disruptive gestures.',
        'workshop': 'In the workshop, show a practical, safe interaction with the product on a workbench when appropriate. Keep hand placement and object contact realistic.',
        'bakery': 'In the bakery, show a natural interaction with the counter or product when relevant, using a gentle detail move and a wider view.',
        'restaurant': 'In the restaurant, show a natural seated or counter interaction appropriate to the product. Use a calm medium shot and a gentle push-in.',
        'hotel': 'In the hotel room, use a natural unpacking, getting-ready or everyday interaction when it suits the product. Keep luggage handling practical.',
        'nature': 'Outdoors, use a relaxed walk or appropriate product interaction with a gentle tracking view.',
        'studio': 'In the studio, use a controlled product showcase: stable full view, one gentle push-in to a visible detail, then a clean hero hold. Do not rotate the product repeatedly.',
        'dark': 'In the luxury studio, use restrained movement, a slow push-in or slight lateral slide, and a stable hero finish.',
        'minimal': 'In the bright minimal setting, use clean stable framing, one gentle reframing toward a visible detail, and a full-product finish.',
        'auto': 'Choose a believable setting-appropriate action based on product and location. Use natural walking or practical interaction when a model is present; use mirror-aware framing for mirror scenes and stable close framing for product use. Avoid repeated spinning, stiff posing and camera moves that fight the action.'
    }
    product_notes = {
        'bag': 'Keep the bag carried or worn naturally, with plausible strap placement and only subtle sway.',
        'hijab': 'Show the hijab through natural head turns and gentle fabric adjustment; do not pull or distort the fabric unnaturally.',
        'fashion': 'Show fit and silhouette through a natural stance, a short walk or one controlled turn only when useful.',
        'shoes': 'Show footwear through natural steps and a brief grounded detail view; do not twist ankles unnaturally.',
        'beauty': 'Show realistic application or handling only when suitable; keep hands away from the face unless the action calls for it.',
        'gadget': 'Use the device in a plausible way with realistic finger placement; keep screens and controls unchanged.',
        'food': 'Handle or present food naturally and safely; do not invent ingredients or extra servings.',
        'home': 'Demonstrate a practical household use with believable contact and scale.',
        'accessory': 'Wear or handle the accessory naturally; avoid repetitive wrist turns or twirling.',
        'travel': 'Handle luggage with believable weight, grip and strap movement; never swing or spin it.'
    }
    location = scene_actions.get(scene_key, scene_actions['auto'])
    product = product_notes.get(product_type, '')
    model = 'Keep body mechanics, gaze, hand placement and walking pace natural.' if model_presence != 'no' else 'No model is required; use stable product framing and a clean product hero shot.'
    return 'ACTION AND CAMERA AUTO-DIRECTION: ' + location + ' ' + product + ' ' + model + ' Choose camera position and movement to support the action, not as a separate effect. Keep motion smooth and purposeful; preserve product identity and spatial continuity.'


def prompt_scene_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✨ Auto (Disyorkan)', callback_data='scene:auto')],
        [InlineKeyboardButton('📸 Studio Premium', callback_data='scene:studio'), InlineKeyboardButton('🌑 Mewah Gelap', callback_data='scene:dark')],
        [InlineKeyboardButton('🏡 Ruang Rumah', callback_data='scene:home'), InlineKeyboardButton('🌿 Alam Semula Jadi', callback_data='scene:nature')],
        [InlineKeyboardButton('☀️ Cerah Minimalis', callback_data='scene:minimal')],
        [InlineKeyboardButton('🍳 Dapur', callback_data='scene:kitchen'), InlineKeyboardButton('🛋️ Ruang Tamu', callback_data='scene:living_room')],
        [InlineKeyboardButton('💼 Pejabat', callback_data='scene:office'), InlineKeyboardButton('🚗 Dalam Kereta', callback_data='scene:car_interior')],
        [InlineKeyboardButton('☕ Kafe', callback_data='scene:cafe'), InlineKeyboardButton('🛍️ Butik', callback_data='scene:boutique')],
        [InlineKeyboardButton('🏬 Pusat Beli-belah', callback_data='scene:mall'), InlineKeyboardButton('💄 Meja Solek', callback_data='scene:vanity')],
        [InlineKeyboardButton('🛏️ Bilik Tidur', callback_data='scene:bedroom'), InlineKeyboardButton('🌿 Taman', callback_data='scene:garden')],
        [InlineKeyboardButton('🏖️ Pantai', callback_data='scene:beach'), InlineKeyboardButton('🏋️ Gimnasium', callback_data='scene:gym')],
        [InlineKeyboardButton('📚 Perpustakaan', callback_data='scene:library'), InlineKeyboardButton('🧰 Bengkel', callback_data='scene:workshop')],
        [InlineKeyboardButton('🥐 Bakeri', callback_data='scene:bakery'), InlineKeyboardButton('🍽️ Restoran', callback_data='scene:restaurant')],
        [InlineKeyboardButton('🧳 Lapangan Terbang', callback_data='scene:airport'), InlineKeyboardButton('🏨 Bilik Hotel', callback_data='scene:hotel')],
        [InlineKeyboardButton('🖼️ Guna Latar Sendiri (Upload ke AI)', callback_data='scene:custom')]
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
    ('Cara jana prompt video', 'Hantar 1–4 gambar produk yang jelas, kemudian pilih kategori, gaya dan durasi.', ('GAMBAR PRODUK', 'PILIH GAYA', 'JANA PROMPT')),
    ('Apa yang diperlukan?', 'Hanya gambar produk yang jelas. Aliran Jana Prompt Video tidak menggunakan pautan Shopee dan tidak memerlukan maklumat daripada halaman Shopee.', ('GAMBAR SAHAJA', 'PILIH DURASI', 'JANA PROMPT')),
    ('Pilihan durasi prompt', 'Pilih 10 saat dengan 1 prompt, 20 saat dengan 2 prompt bersambung atau 1 prompt, atau 30 saat dengan 3 prompt bersambung atau 1 prompt.', ('10 SAAT', '20 SAAT', '30 SAAT')),
    ('Latar gambar', 'Untuk aliran suntingan video, anda boleh kekalkan latar asal atau pilih latar lain. Hasil pengasingan bergantung pada kerumitan gambar.', ('LATAR ASAL', 'PILIH LATAR', 'SEMAK HASIL')),
    ('Fungsi Prompt', 'Prompt ialah arahan teks untuk digunakan dalam penjana video AI. Klippo menyediakan prompt; ia bukan fail video yang telah siap.', ('PILIH PROMPT', 'ISI PILIHAN', 'SALIN TEKS')),
    ('Video gagal dijana', 'Cuba gambar produk yang lebih jelas dan pastikan produk kelihatan penuh. Jika masalah berulang, simpan mesej ralat untuk semakan.', ('SEMAK GAMBAR', 'CUBA SEMULA', 'SIMPAN RALAT')),
    ('Adakah video generatif?', 'Aliran suntingan video menggerakkan gambar dengan animasi 2D, transisi dan muzik. Jana Prompt Video pula menghasilkan teks arahan untuk penjana video AI.', ('SUNTINGAN 2D', 'PROMPT TEKS', 'PILIH ALIRAN')),
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


async def prompt_access_status(user_id):
    """Check subscription and persistent prompt-trial usage; fail closed if DB is unavailable."""
    if not klippo_db.configured():
        return {"available": False, "active": False, "used": 0, "allowed": False}
    try:
        active = await asyncio.to_thread(klippo_db.is_active_subscription, user_id)
        if active:
            return {"available": True, "active": True, "used": 0, "allowed": True}
        trial = await asyncio.to_thread(klippo_db.prompt_trial_status, user_id)
        used = int(trial.get("successful_count", 0))
        return {"available": True, "active": False, "used": used, "allowed": used < 3}
    except Exception:
        logging.exception("Klippo access/trial lookup failed for user %s", user_id)
        return {"available": False, "active": False, "used": 0, "allowed": False}


async def require_paid_feature(message, user_id):
    """Block video-processing features unless the user's subscription is active."""
    access = await prompt_access_status(user_id)
    if access["available"] and access["active"]:
        return True
    if not access["available"]:
        await message.reply_text(
            "⚠️ Status langganan belum dapat disahkan. Fungsi ini dikunci buat sementara. "
            "Sila cuba lagi kemudian atau buka Langganan."
        )
    else:
        await message.reply_text(
            "🔒 Fungsi ini untuk pelanggan Klippo yang mempunyai langganan aktif.\n\n"
            "Trial percuma hanya membenarkan 3 kali Jana Prompt yang berjaya. "
            "Langganan membuka Gerakkan Foto (Transisi), Gabung Video dan Tukar Format Video.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Lihat Langganan", callback_data="subscription")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="home")],
            ])
        )
    return False


async def record_prompt_trial_success(context, user_id):
    """Record a trial only after a prompt result has been successfully delivered."""
    if not context.user_data.get("_prompt_trial_count_on_success"):
        return
    try:
        count = await asyncio.to_thread(klippo_db.record_prompt_trial_success, user_id)
        context.user_data["_prompt_trial_count_on_success"] = False
        logging.info("Klippo prompt trial recorded for user %s; successful_count=%s", user_id, count)
    except Exception:
        context.user_data["_prompt_trial_count_on_success"] = False
        logging.exception("Could not record successful Klippo prompt trial for user %s", user_id)


def main_menu(user_id=None):
    rows = [
        [InlineKeyboardButton('✍️ Jana Prompt', callback_data='prompt')],
        [InlineKeyboardButton('🎞️ Gerakkan Foto (Transisi)', callback_data='make')],
        [InlineKeyboardButton('🎞️ Gabung Video', callback_data='merge')],
        [InlineKeyboardButton('🔄 Tukar Format Video', callback_data='convert')],
        [InlineKeyboardButton('💎 Langganan', callback_data='subscription'), InlineKeyboardButton('👤 Akaun Saya', callback_data='account')],
        [InlineKeyboardButton('💬 Komen & Cadangan', callback_data='feedback')],
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
    """Suggest a natural Malaysian-Malay spoken opening without unsupported claims."""
    import random

    info = ' '.join((info or '').split())[:100]
    if not info or not re.fullmatch(r"[\w\s.,&+()/-]+", info, flags=re.UNICODE):
        return None
    if len(info) > 42:
        info = info[:42].rsplit(' ', 1)[0]
    # A visual-only opening is often more natural than forcing a spoken hook.
    rng = random.SystemRandom()
    if rng.randrange(5) == 0:
        return None
    openings = (
        f"Kalau tengah cari {info}, boleh tengok pilihan ini.",
        f"Sedang bandingkan {info}? Ini satu pilihan untuk dipertimbangkan.",
        f"Kalau minat {info}, boleh semak yang ini.",
        f"Nak cari {info}? Cuba lihat pilihan ini dulu.",
        f"Untuk yang mencari {info}, boleh pertimbangkan pilihan ini.",
    )
    return rng.choice(openings)


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
        'navy': ((73, 92, 124), (25, 37, 59)),
        'sage': ((232, 239, 224), (165, 185, 157)),
        'sky': ((241, 249, 255), (167, 204, 228)),
        'lavender': ((247, 241, 255), (197, 182, 221)),
        'rose': ((255, 241, 241), (219, 170, 176)),
        'mint': ((240, 251, 245), (163, 208, 188)),
        'terracotta': ((246, 222, 208), (163, 91, 67)),
        'charcoal': ((96, 97, 105), (30, 31, 36)),
        'sky_gradient': ((245, 250, 255), (151, 194, 222)),
        'lavender_gradient': ((250, 246, 255), (190, 174, 222)),
        'sage_gradient': ((246, 249, 239), (159, 181, 151)),
        'blush_gradient': ((255, 246, 243), (225, 173, 178)),
        'midnight_gradient': ((91, 99, 121), (19, 24, 38)),
        'sand_gradient': ((255, 249, 235), (193, 157, 115)),
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
    context.user_data['prompt_library_id'] = ''
    context.user_data['prompt_library_storyboard'] = []
    context.user_data['prompt_reference_photos'] = []
    context.user_data['prompt_model_presence'] = 'none'
    context.user_data['prompt_model_count'] = 0
    context.user_data['prompt_model_gender'] = 'none'
    context.user_data['prompt_model_hijab'] = 'na'
    context.user_data['prompt_model_ethnicity'] = 'na'
    context.user_data['prompt_model_age'] = 'na'
    context.user_data['prompt_language'] = 'Malay'
    context.user_data['prompt_voiceover_mode'] = 'none'
    context.user_data['prompt_voiceover_style'] = 'ai'
    context.user_data['prompt_voiceover_script'] = ''
    context.user_data['stage'] = 'home'



async def show_admin_users(message, status='all', offset=0, search_query=''):
    """Render the admin-only user list with status filters and pagination."""
    status = status if status in ('all', 'active', 'expired', 'inactive') else 'all'
    result = await asyncio.to_thread(klippo_db.users, search_query, status, offset, 8)
    items = result['items']
    heading = '👥 SENARAI PENGGUNA KLIPPO'
    if search_query:
        heading += f'\nCarian: {search_query}'
    heading += f"\nPenapis: {status.title()}\nJumlah padanan: {result['total']}"
    keyboard = [
        [InlineKeyboardButton('Semua', callback_data='admin_users:all:0'),
         InlineKeyboardButton('Aktif', callback_data='admin_users:active:0')],
        [InlineKeyboardButton('Tamat', callback_data='admin_users:expired:0'),
         InlineKeyboardButton('Tidak aktif', callback_data='admin_users:inactive:0')],
    ]
    for user in items:
        name = (user.get('telegram_name') or 'Tanpa nama').strip()
        label = f"{name[:24]} · {user['display_status']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"admin_user:{user['telegram_user_id']}:{status}:{offset}")])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton('⬅️ Sebelum', callback_data=f'admin_users:{status}:{max(0, offset-8)}'))
    if offset + len(items) < result['total']:
        nav.append(InlineKeyboardButton('Seterusnya ➡️', callback_data=f'admin_users:{status}:{offset+8}'))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton('🔎 Cara cari pengguna', callback_data='admin_users_help')])
    keyboard.append([InlineKeyboardButton('↩️ Admin', callback_data='admin')])
    if not items:
        heading += '\n\nTiada pengguna ditemui.'
    await message.reply_text(heading, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text('Akses tidak dibenarkan.')
        return
    if not klippo_db.configured():
        await update.effective_message.reply_text('Sambungan Supabase belum tersedia.')
        return
    term = ' '.join(context.args).strip()
    if not term:
        await update.effective_message.reply_text('Cara guna: /cariuser nama atau ID_Telegram')
        return
    await show_admin_users(update.effective_message, 'all', 0, term)


async def show_admin_user_details(message, user_id, status='all', offset=0):
    details = await asyncio.to_thread(klippo_db.user_details, user_id)
    user = details.get('user')
    if not user:
        await message.reply_text('Pengguna tidak ditemui dalam rekod langganan. Pengguna perlu menekan /start untuk didaftarkan.')
        return
    name = user.get('telegram_name') or 'Tanpa nama'
    current = (user.get('status') or 'inactive').lower()
    expiry = user.get('expires_at')
    if current == 'active' and expiry:
        try:
            from datetime import datetime, timezone
            if datetime.fromisoformat(expiry.replace('Z', '+00:00')) <= datetime.now(timezone.utc):
                current = 'expired'
        except (ValueError, TypeError):
            pass
    text = (f"👤 BUTIRAN PENGGUNA KLIPPO\n\nNama: {name}\nID Telegram: {user_id}"
            f"\nStatus: {current}\nMula langganan: {user.get('started_at') or '-'}"
            f"\nTamat langganan: {expiry or '-'}\n\n🧾 SEJARAH RESIT (10 terkini)")
    receipts = details.get('receipts') or []
    if not receipts:
        text += '\nTiada rekod resit.'
    for receipt in receipts:
        text += (f"\n\n#{receipt['id']} · RM{receipt.get('amount_myr') or '5.00'} · {receipt.get('status')}"
                 f"\nDihantar: {receipt.get('submitted_at') or '-'}"
                 f"\nDisemak: {receipt.get('reviewed_at') or '-'}")
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('➕ Tambah 7 hari', callback_data=f'admin_add_days:{user_id}:7:{status}:{offset}'),
         InlineKeyboardButton('➕ Tambah 30 hari', callback_data=f'admin_add_days:{user_id}:30:{status}:{offset}')],
        [InlineKeyboardButton('➕ Tambah 90 hari', callback_data=f'admin_add_days:{user_id}:90:{status}:{offset}'),
         InlineKeyboardButton('➕ Tambah 365 hari', callback_data=f'admin_add_days:{user_id}:365:{status}:{offset}')],
        [InlineKeyboardButton('⬅️ Kembali ke senarai', callback_data=f'admin_users:{status}:{offset}')],
        [InlineKeyboardButton('↩️ Admin', callback_data='admin')]
    ]))


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
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('👥 Senarai Pengguna', callback_data='admin_users:all:0')],
                [InlineKeyboardButton('🧾 Semak Resit', callback_data='admin_pending')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
            ]))
    except Exception:
        logging.exception('Admin Supabase error')
        await update.effective_message.reply_text('⚠️ Gagal menghubungi database. Semak konfigurasi Supabase di Render.')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restore persistent Telegram keyboard and display inline menu."""
    if not context.user_data.get('busy'):
        reset(context)
    if klippo_db.configured():
        try:
            await asyncio.to_thread(klippo_db.register_user, update.effective_user.id, update.effective_user.full_name)
        except Exception:
            logging.exception('Could not register Klippo user in Supabase')
    await update.effective_message.reply_text(
        '🏠 Butang Menu Utama tersedia di bawah ruang menaip.',
        reply_markup=home_keyboard()
    )
    await update.effective_message.reply_text(
        '🎬 KLIPPO | Prompt Video Menarik, Semudah Klik\n\n'
        'Penting: Klippo tidak menjana video AI. Klippo menyediakan prompt teks untuk digunakan di platform video AI pilihan anda.\n\n'
        '⭐ BARU PERTAMA KALI? Mulakan dengan Jana Prompt.\n'
        '🎁 Trial percuma: 3 kali Jana Prompt yang berjaya bagi setiap pengguna.\n'
        'Semasa trial, Transisi, Gabung Video dan Tukar Format Video dikunci sehingga langganan aktif.\n'
        '1️⃣ Jana Prompt — pilih kategori produk, masukkan nama produk, pilih gaya dan durasi, kemudian salin prompt yang siap ke platform video AI.\n'
        '2️⃣ Gerakkan Foto (Transisi) — jadikan gambar pegun sebagai video MP4 dengan gerakan kamera 2D dan muzik; ini bukan penjanaan gerakan AI pada objek.\n'
        '3️⃣ Gabung Video — cantum beberapa klip menjadi satu video.\n'
        '4️⃣ Tukar Format Video — tukar video kepada format MP4 menegak untuk affiliate.\n\n'
        '💎 Langganan — lihat pelan dan cara pembayaran.\n'
        '👤 Akaun Saya — semak status akaun dan langganan.\n\n'
        '💡 Ikut arahan yang muncul selepas setiap pilihan. Jika tersalah pilih, tekan Menu Utama untuk mula semula:',
        reply_markup=main_menu(update.effective_user.id)
    )


async def account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not klippo_db.configured():
        await update.effective_message.reply_text(f'👤 AKAUN SAYA\n\nID Telegram: {user_id}\nStatus langganan belum dapat disemak.')
        return
    try:
        data = await asyncio.to_thread(klippo_db.subscription, user_id)
        active = await asyncio.to_thread(klippo_db.is_active_subscription, user_id)
        status = 'Aktif' if active else ('Tiada langganan aktif' if not data else f"{data['status']} (tamat: {data.get('expires_at') or '-'})")
        trial = await asyncio.to_thread(klippo_db.prompt_trial_status, user_id)
        trial_line = 'Semua fungsi berbayar dibuka.' if active else f"Trial Jana Prompt: {trial['successful_count']}/3 digunakan · {3 - trial['successful_count']} baki."
        await update.effective_message.reply_text(f'👤 AKAUN SAYA\n\nID Telegram: {user_id}\nLangganan: {status}\n{trial_line}')
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
    if context.user_data.get('stage') in ('prompt_upload', 'background_custom_upload'):
        await photo(update, context)
        return
    await receive_receipt(update, context)


async def falbeta_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opt-in AI storyboard/video flow; API calls begin only after a result is chosen."""
    missing = [key for key in ("FAL_KEY", "GEMINI_API_KEY") if not os.environ.get(key, "").strip()]
    if missing:
        await update.effective_message.reply_text(
            "Fungsi Storyboard AI belum dikonfigurasi di Render. Pentadbir perlu menetapkan "
            "FAL_KEY dan GEMINI_API_KEY dalam Environment Variables. Jangan hantar kunci dalam chat."
        )
        return
    context.user_data["stage"] = "fal_beta_photo"
    context.user_data.pop("fal_beta_image", None)
    context.user_data.pop("fal_beta_goal", None)
    await update.effective_message.reply_text(
        "🎬 KLIPPO | STORYBOARD AI\n\nHantar satu gambar produk. Selepas itu pilih tujuan dan hasil. "
        "Penjanaan menggunakan API AI dan mungkin menggunakan kredit berbayar."
    )


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('busy'):
        await update.message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    if context.user_data.get('stage') == 'receipt_upload':
        await receive_receipt(update, context)
        return
    if context.user_data.get('stage') == 'fal_beta_photo':
        if not update.message.photo:
            await update.message.reply_text('Sila hantar gambar produk sebagai gambar Telegram.')
            return
        photo_item = update.message.photo[-1]
        if (photo_item.file_size or 0) > 12 * 1024 * 1024:
            await update.message.reply_text('Gambar terlalu besar. Cuba hantar gambar yang lebih kecil.')
            return
        try:
            tg_file = await photo_item.get_file()
            raw = bytes(await tg_file.download_as_bytearray())
            if not raw or len(raw) > 12 * 1024 * 1024:
                await update.message.reply_text('Gambar tidak sah atau terlalu besar.')
                return
            context.user_data['fal_beta_image'] = raw
            context.user_data['stage'] = 'fal_beta_goal'
            await update.message.reply_text(
                'Pilih tujuan kandungan:',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton('🛍️ Shopee Affiliate', callback_data='falbeta:goal:shopee'),
                    InlineKeyboardButton('🎵 TikTok Viral', callback_data='falbeta:goal:tiktok'),
                ]])
            )
        except Exception:
            logging.exception('Klippo beta image upload failed')
            await update.message.reply_text('Tidak berjaya menerima gambar. Cuba hantar semula.')
        return
    if context.user_data.get('stage') == 'background_custom_upload':
        photo_item = update.message.photo[-1] if update.message.photo else update.message.document
        if not update.message.photo and not (update.message.document and (update.message.document.mime_type or '').startswith('image/')):
            await update.message.reply_text('Sila hantar gambar latar sebagai gambar atau fail imej (JPG, PNG atau WEBP).')
            return
        context.user_data['custom_background_file_id'] = photo_item.file_id
        context.user_data['background'] = 'custom'
        context.user_data['stage'] = 'duration'
        await update.message.reply_text('✅ Gambar latar sendiri diterima. Pilih durasi video:', reply_markup=duration_menu())
        return
    if context.user_data.get('stage') == 'prompt_images':
        if not update.message.photo:
            await update.message.reply_text('Sila hantar gambar produk sebagai gambar Telegram. Maksimum 4 gambar.', reply_markup=prompt_images_menu())
            return
        images = context.user_data.setdefault('prompt_reference_photos', [])
        if len(images) >= 4:
            await update.message.reply_text('Maksimum 4 gambar telah diterima. Tekan Selesai Hantar Gambar untuk meneruskan.', reply_markup=prompt_images_menu())
            return
        images.append(update.message.photo[-1].file_id)
        await update.message.reply_text(f'✅ Gambar {len(images)}/4 diterima. Hantar lagi atau tekan Selesai Hantar Gambar.', reply_markup=prompt_images_menu())
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
        await query.message.reply_text(
            '🎬 KLIPPO | Prompt Video Menarik, Semudah Klik\n\n'
            'Klippo tidak menjana video AI. Fungsi Jana Prompt menyediakan teks arahan untuk digunakan di platform video AI pilihan anda.\n\n'
            'Pilih fungsi di bawah. Baru pertama kali? Mulakan dengan ✍️ Jana Prompt.\n'
            'Ikut arahan satu demi satu; tekan Menu Utama jika mahu mula semula.',
            reply_markup=main_menu(update.effective_user.id)
        )
        return
    if context.user_data.get('busy'):
        await query.message.reply_text('Video sedang diproses. Sila tunggu.')
        return
    stage = context.user_data.get('stage', 'home')
    paid_actions = action in ('make', 'merge', 'convert', 'storyboard', 'falbeta')
    paid_actions = paid_actions or action.startswith(('merge_', 'video_input:'))
    if paid_actions and not await require_paid_feature(query.message, update.effective_user.id):
        return

    if action == 'falbeta':
        missing = [key for key in ("FAL_KEY", "GEMINI_API_KEY") if not os.environ.get(key, "").strip()]
        if missing:
            await query.message.reply_text(
                "Storyboard AI belum dikonfigurasi. Pentadbir perlu menetapkan FAL_KEY dan GEMINI_API_KEY "
                "di Render Environment Variables. Jangan hantar kunci dalam chat."
            )
            return
        context.user_data['stage'] = 'fal_beta_photo'
        context.user_data.pop('fal_beta_image', None)
        context.user_data.pop('fal_beta_goal', None)
        await query.message.reply_text(
            "🎬 KLIPPO | STORYBOARD AI\n\nHantar satu gambar produk. Selepas itu pilih tujuan dan hasil. "
            "Penjanaan menggunakan API AI dan mungkin menggunakan kredit berbayar."
        )
        return
    if action.startswith('falbeta:goal:'):
        goal = action.rsplit(':', 1)[-1]
        if not context.user_data.get('fal_beta_image'):
            await query.message.reply_text('Sila hantar gambar produk dahulu melalui Storyboard AI.')
            return
        context.user_data['fal_beta_goal'] = goal
        await query.edit_message_text(
            'Pilih hasil. Penjanaan video/gambar menggunakan API AI dan mungkin menggunakan kredit berbayar:',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🖼️ Jana 2 Panel Storyboard', callback_data='falbeta:format:image')],
                [InlineKeyboardButton('🎬 Jana Video Motion + Voiceover', callback_data='falbeta:format:video')],
            ])
        )
        return
    if action.startswith('falbeta:format:'):
        output_format = action.rsplit(':', 1)[-1]
        raw = context.user_data.get('fal_beta_image')
        if not raw:
            await query.edit_message_text('Sesi gambar tamat. Tekan Storyboard AI untuk mula semula.')
            return
        if not os.environ.get('FAL_KEY', '').strip() or not os.environ.get('GEMINI_API_KEY', '').strip():
            await query.edit_message_text('Fungsi belum dikonfigurasi. Pentadbir perlu menetapkan FAL_KEY dan GEMINI_API_KEY dalam Render.')
            return
        context.user_data['busy'] = True
        try:
            await query.edit_message_text('Menganalisis produk dan menjana dua panel AI. Sila tunggu…')
            from fal_storyboard_test import analyze_product, generate_panel
            from modules.video_engine import create_video
            import fal_client
            with tempfile.TemporaryDirectory(prefix='klippo-falbeta-') as temp:
                root = Path(temp)
                image_path = root / 'product_reference.jpg'
                image_path.write_bytes(raw)
                attributes = await asyncio.to_thread(analyze_product, image_path)
                image_url = await asyncio.to_thread(fal_client.upload_file, str(image_path))
                goal = context.user_data.get('fal_beta_goal', 'shopee')
                goal_scene = (
                    'Shopee affiliate product showcase, clear product visibility and trustworthy commercial styling.'
                    if goal == 'shopee' else
                    'TikTok-style energetic visual hook, dynamic but believable framing; keep the product clearly visible.'
                )
                scenes = [
                    'Opening hero shot: product clearly visible in a tasteful clean setting, three-quarter view.',
                    'Detail shot: closer framing on the same product, showing only real visible details and gentle highlights.',
                ]
                panel_paths = []
                panel_bytes = []
                from PIL import Image
                for index, scene in enumerate(scenes, start=1):
                    data, _latency = await asyncio.to_thread(
                        generate_panel, image_url, attributes, f'{goal_scene} {scene}', index
                    )
                    panel_path = root / f'panel_{index}.jpg'
                    with Image.open(BytesIO(data)) as generated_image:
                        generated_image.convert('RGB').save(panel_path, 'JPEG', quality=92, optimize=True)
                    panel_paths.append(panel_path)
                    panel_bytes.append(panel_path.read_bytes())
                if output_format == 'image':
                    for index, data in enumerate(panel_bytes, start=1):
                        await query.message.reply_photo(
                            photo=BytesIO(data),
                            caption=f'Storyboard AI — Panel {index}/2. Semak kesamaan bentuk, warna, logo dan butiran produk.'
                        )
                else:
                    voiceover = str(attributes.get('voiceover_ms') or
                        'Lihat produk ini dengan reka bentuk dan perincian yang menarik.')
                    video_path = root / 'klippo_product_video.mp4'
                    await query.message.reply_text('Panel siap. Sedang menghasilkan video 9:16 dan voiceover Bahasa Melayu…')
                    await asyncio.to_thread(create_video, panel_paths, voiceover, video_path)
                    with video_path.open('rb') as video_file:
                        await query.message.reply_video(
                            video=video_file,
                            caption='Video Storyboard AI beta 9:16 dengan motion + voiceover.',
                            supports_streaming=True
                        )
            context.user_data['stage'] = 'home'
            context.user_data.pop('fal_beta_image', None)
            await query.message.reply_text('Selesai. Untuk jana lagi, pilih Storyboard AI daripada menu.')
        except Exception as exc:
            logging.exception('Klippo Storyboard AI generation failed')
            # Give a safe, actionable message for fal.ai storage authentication failures.
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status_code == 403 and 'fal' in str(getattr(exc, 'request', '')) .lower():
                user_message = (
                    '❌ fal.ai menolak pengesahan storan (HTTP 403). Gemini berjaya, tetapi gambar belum '
                    'dimuat naik dan penjanaan belum bermula. Pentadbir: semak FAL_KEY dalam Render '
                    'Environment dan gantikannya dengan API key aktif dari https://fal.ai/dashboard/keys, '
                    'kemudian redeploy. Jangan hantar API key dalam chat.'
                )
            elif status_code == 403:
                user_message = (
                    '❌ Permintaan AI ditolak (HTTP 403). Semak kunci API/akses penyedia dalam Render. '
                    'Jangan hantar API key dalam chat.'
                )
            else:
                user_message = (
                    'Penjanaan gagal. Semak log Render dan penggunaan API. Bot utama masih menggunakan aliran sedia ada.'
                )
            await query.message.reply_text(user_message)
        finally:
            context.user_data.pop('busy', None)
        return
    if action.startswith('admin_users:'):
        if not is_admin(update.effective_user.id):
            await query.message.reply_text('Akses tidak dibenarkan.')
            return
        if not klippo_db.configured():
            await query.message.reply_text('Sambungan Supabase belum tersedia.')
            return
        try:
            _, user_status, raw_offset = action.split(':', 2)
            await show_admin_users(query.message, user_status, int(raw_offset))
        except Exception:
            logging.exception('Admin user list failed')
            await query.message.reply_text('Gagal mendapatkan senarai pengguna daripada database.')
    elif action.startswith('admin_user:'):
        if not is_admin(update.effective_user.id):
            await query.message.reply_text('Akses tidak dibenarkan.')
            return
        try:
            _, raw_id, user_status, raw_offset = action.split(':', 3)
            await show_admin_user_details(query.message, int(raw_id), user_status, int(raw_offset))
        except Exception:
            logging.exception('Admin user detail failed')
            await query.message.reply_text('Gagal mendapatkan butiran pengguna.')
    elif action.startswith('admin_add_days:'):
        if not is_admin(update.effective_user.id):
            await query.message.reply_text('Akses tidak dibenarkan.')
            return
        if not klippo_db.configured():
            await query.message.reply_text('Sambungan Supabase belum tersedia.')
            return
        try:
            _, raw_id, raw_days, user_status, raw_offset = action.split(':', 4)
            user_id, days, offset = int(raw_id), int(raw_days), int(raw_offset)
            if days not in (7, 30, 90, 365):
                raise ValueError('Invalid subscription extension')
            updated = await asyncio.to_thread(klippo_db.add_subscription_days, user_id, days)
            expiry = updated.get('expires_at') or '-'
            await query.message.reply_text(
                f'✅ Langganan dikemas kini.\nPengguna: {updated.get("telegram_name") or user_id}'
                f'\nTempoh ditambah: {days} hari\nTarikh tamat baharu: {expiry}'
            )
            await show_admin_user_details(query.message, user_id, user_status, offset)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f'🎉 Admin telah menambah {days} hari langganan Klippo anda. Langganan aktif sehingga {expiry}.'
                )
            except Exception:
                logging.info('Could not notify user %s about subscription extension', user_id, exc_info=True)
        except Exception:
            logging.exception('Admin subscription extension failed')
            await query.message.reply_text('❌ Gagal menambah hari langganan. Semak rekod pengguna dan sambungan database.')
    elif action == 'admin_users_help':
        if not is_admin(update.effective_user.id):
            await query.message.reply_text('Akses tidak dibenarkan.')
            return
        await query.message.reply_text('🔎 Untuk mencari nama atau ID Telegram, gunakan arahan admin:\n/cariuser nama\n/cariuser 123456789')
    elif action == 'admin_pending':
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
        context.user_data['prompt_mode'] = 'normal'
        context.user_data['prompt_reference_photos'] = []
        context.user_data['prompt_duration_mode'] = 'single'
        context.user_data['prompt_product_type'] = ''
        context.user_data['prompt_product_subcategory'] = ''
        context.user_data['prompt_product_name'] = ''
        context.user_data['prompt_custom_category_name'] = ''
        context.user_data['prompt_custom_subcategory_name'] = ''
        context.user_data['stage'] = 'prompt_product_type'
        await query.message.reply_text(
            '✍️ KLIPPO | JANA PROMPT VIDEO\n\nPilih kategori dan subkategori produk dahulu. Selepas nama produk, anda boleh pilih model manusia, haiwan (jika sesuai) atau fokus produk sahaja sebelum memilih gaya video.\n\nGambar produk tidak perlu dimuat naik ke bot.',
            reply_markup=prompt_product_type_menu()
        )
    elif action.startswith('prompt_mode:'):
        selected_mode = action.split(':', 1)[1]
        if selected_mode not in ('video', 'storyboard'):
            await query.message.reply_text(
                'Pilihan tidak sah. Sila pilih semula.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('🎥 Jana Prompt Video', callback_data='prompt_mode:video')],
                    [InlineKeyboardButton('🧩 Jana Prompt Storyboard', callback_data='prompt_mode:storyboard')]
                ])
            )
        else:
            context.user_data['prompt_mode'] = 'normal'
            context.user_data['prompt_reference_photos'] = []
            context.user_data['stage'] = 'prompt_product_type'
            instruction = '🎥 JANA PROMPT VIDEO\n\nMuat naik gambar tidak diperlukan. Pilih kategori, subkategori dan nama produk; kemudian pilih latar, gaya dan durasi.'
            await query.message.reply_text(instruction, reply_markup=prompt_product_type_menu())
    elif action.startswith('prompt_flow:'):
        # Compatibility for old Telegram keyboards: both legacy buttons now enter
        # the same single prompt flow, never the storyboard branch.
        context.user_data['prompt_mode'] = 'normal'
        context.user_data['prompt_reference_photos'] = []
        context.user_data['stage'] = 'prompt_product_type'
        await query.message.reply_text(
            '✍️ JANA PROMPT VIDEO\n\nMuat naik gambar tidak diperlukan. Pilih kategori, subkategori dan nama produk untuk meneruskan.',
            reply_markup=prompt_product_type_menu()
        )
    elif action == 'prompt_images_done' and stage == 'prompt_images':
        if not context.user_data.get('prompt_reference_photos'):
            await query.message.reply_text('Sila hantar sekurang-kurangnya 1 gambar produk dahulu.', reply_markup=prompt_images_menu())
        else:
            context.user_data['stage'] = 'prompt_product_type'
            await query.message.reply_text(
                f"✅ {len(context.user_data['prompt_reference_photos'])} gambar diterima.\n\n📦 Pilih kategori produk:",
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
            await query.message.reply_text('⏱️ Pilih tempoh dan cara susunan prompt video:', reply_markup=prompt_duration_menu())
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
            context.user_data['prompt_library_id'] = prompt_id
            context.user_data['prompt_library_storyboard'] = _prompt_library_storyboard(template)
            if context.user_data.get('prompt_product_name'):
                product_name = context.user_data['prompt_product_name']
                subtype = detect_product_subtype(product_name)
                context.user_data['prompt_bag_subtype'] = detect_bag_subtype(product_name)
                category_product_type = {
                    'clothing': 'fashion',
                    'bags': 'bag',
                    'wallets': 'wallet',
                    'shoes': 'shoes',
                    'beauty': 'beauty',
                    'gadgets': 'gadget',
                    'home': 'home',
                    'accessories': 'accessory',
                    'food': 'food',
                    'stationery': 'other',
                    'sports': 'other',
                    'travel': 'travel',
                    'pets': 'pet',
                    'automotive': 'automotive',
                    'garden': 'garden',
                    'kitchen': 'kitchen',
                    'furniture': 'furniture',
                    'baby': 'baby',
                    'crafts': 'crafts',
                }
                if subtype == 'hijab':
                    context.user_data['prompt_product_type'] = 'hijab'
                else:
                    context.user_data['prompt_product_type'] = category_product_type.get(category_id, 'other')
                context.user_data['stage'] = 'prompt_scene'
                await query.message.reply_text(
                    '✅ Nama produk: ' + product_name + '\n🔎 Jenis dikesan: ' + (subtype.replace('_', ' ') if subtype else category_id) + '\n\n🎨 Pilih latar video:',
                    reply_markup=prompt_scene_menu()
                )
            else:
                context.user_data['stage'] = 'prompt_product_name'
                await query.message.reply_text('🛍️ Masukkan nama produk daripada Shopee. Nama sahaja — gambar dan pautan tidak diperlukan.')
    elif action == 'prompt_product_categories':
        context.user_data['stage'] = 'prompt_product_type'
        await query.message.reply_text('📦 Pilih kategori produk:', reply_markup=prompt_product_type_menu())
    elif action.startswith('prompt_product_type:'):
        selected = action.split(':', 1)[1]
        if selected == 'custom':
            context.user_data['prompt_custom_category_parent'] = 'category'
            context.user_data['stage'] = 'prompt_custom_category'
            await query.message.reply_text('✏️ Taip kategori produk anda sendiri. Contoh: Peralatan memancing atau Aksesori akuarium.')
        elif selected in PRODUCT_TYPES:
            context.user_data['prompt_product_type'] = selected
            context.user_data['prompt_product_subcategory'] = ''
            context.user_data['prompt_custom_category_name'] = ''
            context.user_data['prompt_custom_subcategory_name'] = ''
            context.user_data['stage'] = 'prompt_product_subcategory'
            await query.message.reply_text(
                f"📦 Kategori: {PRODUCT_TYPES[selected]}\n\n🔎 Pilih subkategori produk:",
                reply_markup=prompt_product_subtype_menu(selected)
            )
        else:
            await query.message.reply_text('Pilihan produk tidak sah. Sila pilih semula:', reply_markup=prompt_product_type_menu())
    elif action.startswith('prompt_product_subcategory:') and stage == 'prompt_product_subcategory':
        selected = action.split(':', 1)[1]
        category = context.user_data.get('prompt_product_type', 'other')
        valid = {slug for slug, _label in PRODUCT_SUBTYPES.get(category, [])}
        if selected == 'custom':
            context.user_data['prompt_custom_category_parent'] = 'subcategory'
            context.user_data['stage'] = 'prompt_custom_category'
            await query.message.reply_text('✏️ Taip subkategori produk anda sendiri. Contoh: Beg kamera kalis air atau serum rambut.')
        elif selected in valid:
            context.user_data['prompt_product_subcategory'] = selected
            context.user_data['prompt_custom_category_name'] = ''
            context.user_data['prompt_custom_subcategory_name'] = ''
            context.user_data['stage'] = 'prompt_product_name'
            await query.message.reply_text(
                f"✅ Subkategori: {PRODUCT_SUBTYPE_LABELS[selected]}\n\n🛍️ Masukkan nama produk (nama sahaja, bukan pautan):"
            )
        else:
            await query.message.reply_text('Pilihan subkategori tidak sah. Sila pilih semula:', reply_markup=prompt_product_subtype_menu(category))
    elif action.startswith('prompt_setup:') and stage in ('prompt_setup_mode', 'prompt_confirm'):
        selected = action.split(':', 1)[1]
        if selected == 'auto':
            product_type = context.user_data.get('prompt_product_type', 'other')
            auto_model_defaults = auto_prompt_model_defaults(
                product_type=product_type,
                product_subcategory=context.user_data.get('prompt_product_subcategory', ''),
                child_product=_prompt_is_child_product(context.user_data),
                animal_related=_prompt_is_animal_related(context.user_data),
            )
            context.user_data.update({
                **auto_model_defaults,
                'prompt_model_gender_2':'none','prompt_model_hijab_2':'na','prompt_model_age_2':'na',
                'prompt_style':'auto','prompt_language':'Malay','prompt_voiceover_mode':'ai','prompt_voiceover_style':'auto',
                'prompt_speech_source':'voiceover','prompt_voiceover_script':'','prompt_concept':'',
                'prompt_scene':'clean premium studio background, selected to complement the exact product reference',
                'prompt_motion_choice':'auto','prompt_framing':'auto','prompt_ad_angle':'auto','prompt_on_screen_text':'no','prompt_text_mode':'auto',
                'prompt_text_content':'','prompt_audio_enabled':True,'stage':'prompt_ad_angle','prompt_ad_angle_flow':'auto_setup'
            })
            await query.message.reply_text('🎯 Pilih pendekatan iklan untuk hook, jalan cerita dan CTA:', reply_markup=prompt_ad_angle_menu())
        elif selected == 'manual':
            context.user_data['stage'] = 'prompt_model_presence'
            await query.message.reply_text('👤 Pilih model untuk video:', reply_markup=prompt_model_presence_menu(context.user_data))
    elif action.startswith('prompt_model:') and stage == 'prompt_model_presence':
        selected = action.split(':', 1)[1]
        if selected == 'none':
            context.user_data.update({'prompt_model_presence':'none','prompt_model_count':0,'prompt_model_gender':'none','prompt_model_hijab':'na','prompt_model_ethnicity':'na','prompt_model_age':'na','prompt_model_gender_2':'none','prompt_model_hijab_2':'na','prompt_model_age_2':'na'})
            context.user_data['stage'] = 'prompt_style'
            await query.message.reply_text('🎨 Pilih gaya video:', reply_markup=prompt_style_menu(context.user_data.get('prompt_product_type','other'),'none'))
        elif selected == 'yes':
            context.user_data['prompt_model_presence'] = 'yes'
            context.user_data['stage'] = 'prompt_model_count'
            await query.message.reply_text('👥 Berapa orang model yang diperlukan?', reply_markup=prompt_model_count_menu())
        elif selected == 'animal' and _prompt_is_animal_related(context.user_data):
            context.user_data.update({
                'prompt_model_presence': 'animal',
                'prompt_model_count': 1,
                'prompt_model_gender': 'none',
                'prompt_model_age': 'na',
                'prompt_model_ethnicity': 'na',
            })
            context.user_data['stage'] = 'prompt_animal_species'
            await query.message.reply_text('🐾 Pilih haiwan yang menjadi model:', reply_markup=prompt_animal_species_menu())
    elif action.startswith('prompt_animal_species:') and stage == 'prompt_animal_species':
        selected = action.split(':', 1)[1]
        if selected in {'auto', 'cat', 'dog', 'rabbit', 'bird', 'hamster', 'fish', 'horse'}:
            context.user_data['prompt_animal_species'] = selected
            context.user_data['stage'] = 'prompt_style'
            await query.message.reply_text('🎨 Pilih gaya video:', reply_markup=prompt_style_menu(context.user_data.get('prompt_product_type', 'other'), 'animal'))
    elif action.startswith('prompt_model_count:') and stage == 'prompt_model_count':
        selected = action.split(':', 1)[1]
        if selected in ('1','2'):
            context.user_data['prompt_model_count'] = int(selected)
            context.user_data.update({'prompt_model_gender_2':'none','prompt_model_hijab_2':'na','prompt_model_age_2':'na'})
            context.user_data['stage'] = 'prompt_model_gender'
            await query.message.reply_text('Pilih jantina model pertama:', reply_markup=prompt_model_gender_menu())
    elif action.startswith('prompt_model_gender:') and stage in ('prompt_model_gender','prompt_model_gender_2'):
        selected = action.split(':', 1)[1]
        if selected in ('auto','female','male'):
            if stage == 'prompt_model_gender_2':
                context.user_data['prompt_model_gender_2'] = selected
                context.user_data['stage'] = 'prompt_model_age_2'
                await query.message.reply_text('Pilih umur model kedua:', reply_markup=prompt_model_age_menu())
            else:
                context.user_data['prompt_model_gender'] = selected
                context.user_data['stage'] = 'prompt_model_age'
                await query.message.reply_text('Pilih umur model pertama:', reply_markup=prompt_model_age_menu())
    elif action.startswith('prompt_model_age:') and stage in ('prompt_model_age','prompt_model_age_2'):
        selected = action.split(':', 1)[1]
        if selected in ('4-7','8-12','13-17','18-25','26-40','41-60','60+'):
            if selected in ('4-7','8-12','13-17') and not _prompt_is_child_product(context.user_data):
                await query.message.reply_text('⚠️ Model bawah 18 tahun hanya sesuai untuk produk kanak-kanak atau remaja. Untuk produk lain, pilih umur dewasa.', reply_markup=prompt_model_age_menu())
                return
            if stage == 'prompt_model_age_2':
                context.user_data['prompt_model_age_2'] = selected
                context.user_data['prompt_model_ethnicity_2'] = 'random_malaysia'
                context.user_data['prompt_ethnicity_target'] = 2
                context.user_data['stage'] = 'prompt_model_ethnicity'
                await query.message.reply_text('Pilih penampilan kaum untuk model kedua:', reply_markup=prompt_model_ethnicity_menu())
            else:
                context.user_data['prompt_model_age'] = selected
                context.user_data['prompt_model_ethnicity'] = 'random_malaysia'
                context.user_data['prompt_ethnicity_target'] = 1
                context.user_data['stage'] = 'prompt_model_ethnicity'
                await query.message.reply_text('Pilih penampilan kaum untuk model pertama:', reply_markup=prompt_model_ethnicity_menu())
    elif action.startswith('prompt_model_ethnicity:') and stage == 'prompt_model_ethnicity':
        selected = action.split(':', 1)[1]
        if selected in ('Malay', 'Chinese', 'Indian', 'random_malaysia'):
            target = int(context.user_data.get('prompt_ethnicity_target', 1))
            if target == 2:
                context.user_data['prompt_model_ethnicity_2'] = selected
                if context.user_data.get('prompt_model_gender_2') == 'female':
                    context.user_data['prompt_hijab_target'] = 2
                    context.user_data['stage'] = 'prompt_model_hijab'
                    await query.message.reply_text('Model kedua wanita — pilih bertudung atau tidak:', reply_markup=prompt_model_hijab_menu())
                elif context.user_data.get('prompt_model_gender') == 'female':
                    context.user_data['prompt_hijab_target'] = 1
                    context.user_data['stage'] = 'prompt_model_hijab'
                    await query.message.reply_text('Model pertama wanita — pilih bertudung atau tidak:', reply_markup=prompt_model_hijab_menu())
                else:
                    context.user_data['stage'] = 'prompt_style'
                    await query.message.reply_text('🎨 Pilih gaya video:', reply_markup=prompt_style_menu(context.user_data.get('prompt_product_type','other'),'yes'))
            else:
                context.user_data['prompt_model_ethnicity'] = selected
                if int(context.user_data.get('prompt_model_count', 1)) == 2:
                    context.user_data['stage'] = 'prompt_model_gender_2'
                    await query.message.reply_text('Pilih jantina model kedua:', reply_markup=prompt_model_gender_menu())
                elif context.user_data.get('prompt_model_gender') == 'female':
                    context.user_data['prompt_hijab_target'] = 1
                    context.user_data['stage'] = 'prompt_model_hijab'
                    await query.message.reply_text('Model wanita — pilih bertudung atau tidak:', reply_markup=prompt_model_hijab_menu())
                else:
                    context.user_data['prompt_model_hijab'] = 'na'
                    context.user_data['stage'] = 'prompt_style'
                    await query.message.reply_text('🎨 Pilih gaya video:', reply_markup=prompt_style_menu(context.user_data.get('prompt_product_type','other'),'yes'))
    elif action.startswith('prompt_model_hijab:') and stage == 'prompt_model_hijab':
        selected = action.split(':', 1)[1]
        if selected in ('hijab','no_hijab','na'):
            target = int(context.user_data.get('prompt_hijab_target',1))
            if target == 2:
                context.user_data['prompt_model_hijab_2'] = selected
                if context.user_data.get('prompt_model_gender') == 'female' and context.user_data.get('prompt_model_hijab','na') == 'na':
                    context.user_data['prompt_hijab_target'] = 1
                    await query.message.reply_text('Model pertama wanita — pilih bertudung atau tidak:', reply_markup=prompt_model_hijab_menu())
                    return
            else:
                context.user_data['prompt_model_hijab'] = selected
                if int(context.user_data.get('prompt_model_count',1)) == 2 and context.user_data.get('prompt_model_gender_2') == 'female' and context.user_data.get('prompt_model_hijab_2','na') == 'na':
                    context.user_data['prompt_hijab_target'] = 2
                    await query.message.reply_text('Model kedua wanita — pilih bertudung atau tidak:', reply_markup=prompt_model_hijab_menu())
                    return
            context.user_data['stage'] = 'prompt_style'
            await query.message.reply_text('🎨 Pilih gaya video:', reply_markup=prompt_style_menu(context.user_data.get('prompt_product_type','other'),'yes'))
    elif action.startswith('prompt_duration:') and stage == 'prompt_duration':
        selected = action.split(':', 1)[1]
        valid_duration_modes = {
            '10': (10, 'single'), '20': (20, 'split'), '30': (30, 'split'),
            '10_single': (10, 'single'), '20_single': (20, 'single'), '20_split': (20, 'split'),
            '30_single': (30, 'single'), '30_split': (30, 'split'),
        }
        if selected in valid_duration_modes:
            duration, duration_mode = valid_duration_modes[selected]
            context.user_data['prompt_duration'] = duration
            context.user_data['prompt_duration_mode'] = duration_mode
            context.user_data['prompt_ad_angle'] = 'auto'
            context.user_data.pop('prompt_ad_angle_flow', None)
            context.user_data.setdefault('prompt_language', 'Malay')
            context.user_data.setdefault('prompt_voiceover_mode', 'ai')
            context.user_data.setdefault('prompt_voiceover_style', 'auto')
            context.user_data['prompt_speech_source'] = 'voiceover'
            context.user_data['prompt_voiceover_script'] = ''
            context.user_data['prompt_on_screen_text'] = 'no'
            context.user_data['prompt_text_mode'] = 'none'
            context.user_data['prompt_text_content'] = ''
            context.user_data['prompt_audio_enabled'] = None
            context.user_data['prompt_scene'] = 'a realistic premium location chosen to suit the product, with natural lighting and believable physical surroundings'
            context.user_data['prompt_scene_key'] = 'auto'
            context.user_data['prompt_custom_background'] = False
            context.user_data['prompt_motion_choice'] = 'auto'
            context.user_data['prompt_framing'] = 'auto'
            context.user_data['stage'] = 'prompt_ad_angle'
            await query.message.reply_text(
                '🎯 Pilih pendekatan iklan untuk hook, jalan cerita dan CTA:',
                reply_markup=prompt_ad_angle_menu()
            )
    elif action.startswith('prompt_ad_angle:') and stage == 'prompt_ad_angle':
        selected = action.split(':', 1)[1]
        valid_angles = {'auto', 'question', 'reveal', 'demo', 'relatable', 'premium', 'affiliate'}
        if selected in valid_angles:
            context.user_data['prompt_ad_angle'] = selected
            angle_flow = context.user_data.pop('prompt_ad_angle_flow', None)
            if angle_flow == 'auto_setup':
                context.user_data['stage'] = 'prompt_scene'
                await query.message.reply_text('🖼️ Pilih latar video:', reply_markup=prompt_scene_menu())
            else:
                context.user_data['stage'] = 'prompt_text_presence'
                await query.message.reply_text(
                    '📝 Mahu teks dipaparkan pada skrin video?',
                    reply_markup=prompt_text_presence_menu()
                )
        else:
            await query.message.reply_text(
                'Pilihan pendekatan iklan tidak sah. Sila pilih semula:',
                reply_markup=prompt_ad_angle_menu()
            )
    elif action.startswith('prompt_text_presence:') and stage == 'prompt_text_presence':
        selected = action.split(':', 1)[1]
        if selected in ('yes','no'):
            context.user_data['prompt_on_screen_text'] = selected
            if selected == 'yes':
                context.user_data['stage'] = 'prompt_text_mode'
                await query.message.reply_text('Pilih cara menyediakan teks pada skrin:', reply_markup=prompt_text_mode_menu())
            else:
                context.user_data['prompt_text_mode'] = 'none'
                context.user_data['prompt_text_content'] = ''
                context.user_data['stage'] = 'prompt_audio_presence'
                await query.message.reply_text('🔊 Mahu audio atau suara dalam video?', reply_markup=prompt_audio_presence_menu())
    elif action.startswith('prompt_text_mode:') and stage == 'prompt_text_mode':
        selected = action.split(':', 1)[1]
        if selected == 'auto':
            context.user_data['prompt_text_mode'] = 'auto'
            context.user_data['prompt_text_content'] = ''
            context.user_data['stage'] = 'prompt_audio_presence'
            await query.message.reply_text('🔊 Mahu audio atau suara dalam video?', reply_markup=prompt_audio_presence_menu())
        elif selected == 'manual':
            context.user_data['prompt_text_mode'] = 'manual'
            context.user_data['stage'] = 'prompt_text_content'
            await query.message.reply_text('✍️ Taip teks tepat yang mahu dipaparkan pada skrin video.')
    elif action.startswith('prompt_audio_presence:') and stage == 'prompt_audio_presence':
        selected = action.split(':', 1)[1]
        if selected in ('yes','no'):
            context.user_data['prompt_audio_enabled'] = selected == 'yes'
            if selected == 'no':
                context.user_data['prompt_voiceover_mode'] = 'none'
                context.user_data['prompt_voiceover_style'] = 'none'
                context.user_data['prompt_voiceover_script'] = ''
                context.user_data['stage'] = 'prompt_scene'
                await query.message.reply_text('🖼️ Pilih latar video:', reply_markup=prompt_scene_menu())
            elif context.user_data.get('prompt_model_presence') == 'yes':
                context.user_data['stage'] = 'prompt_speaker'
                await query.message.reply_text('Pilih sumber suara:', reply_markup=prompt_speaker_menu())
            else:
                context.user_data['prompt_speech_source'] = 'voiceover'
                context.user_data['stage'] = 'prompt_language'
                await query.message.reply_text('Pilih bahasa suara:', reply_markup=prompt_language_menu())
    elif action.startswith('prompt_language:') and stage == 'prompt_language':
        selected = action.split(':', 1)[1]
        if selected in ('Malay','English','none'):
            context.user_data['prompt_language'] = selected
            context.user_data['stage'] = 'prompt_voiceover'
            await query.message.reply_text('Pilih Auto atau gaya suara:', reply_markup=prompt_voiceover_menu())
    elif action.startswith('prompt_speaker:') and stage == 'prompt_speaker':
        selected = action.split(':', 1)[1]
        if selected in ('model','voiceover'):
            context.user_data['prompt_speech_source'] = selected
            context.user_data['stage'] = 'prompt_language'
            await query.message.reply_text('Pilih bahasa suara:', reply_markup=prompt_language_menu())
    elif action.startswith('prompt_voiceover:') and stage == 'prompt_voiceover':
        selected = action.split(':', 1)[1]
        valid_voice_styles = {'auto','none','ai','cute','serious','energetic','friendly','soft','script'}
        if selected not in valid_voice_styles:
            await query.message.reply_text('Pilihan suara tidak dikenali. Sila pilih semula.', reply_markup=prompt_voiceover_menu())
        elif selected == 'script':
            context.user_data['prompt_voiceover_mode'] = 'script'
            context.user_data['prompt_voiceover_style'] = 'custom'
            context.user_data['stage'] = 'prompt_voiceover_text'
            await query.message.reply_text('✍️ Taip skrip suara/dialog yang mahu digunakan.')
        else:
            context.user_data['prompt_voiceover_mode'] = 'none' if selected == 'none' else 'ai'
            context.user_data['prompt_voiceover_style'] = selected
            context.user_data['prompt_voiceover_script'] = ''
            context.user_data['stage'] = 'prompt_scene'
            await query.message.reply_text('🖼️ Pilih latar video:', reply_markup=prompt_scene_menu())
    elif action.startswith('prompt_style:') and stage == 'prompt_style':
        selected = action.split(':', 1)[1]
        valid = set(CORE_USER_STYLE_KEYS)
        if selected in valid and selected in {key for key, _ in storyboard_styles()}:
            context.user_data['prompt_style'] = selected
            context.user_data['prompt_motion_choice'] = 'auto'
            context.user_data['prompt_framing'] = 'auto'
            context.user_data['prompt_ad_angle'] = 'auto'
            context.user_data['prompt_scene_key'] = 'auto'
            context.user_data['stage'] = 'prompt_duration'
            style_label = CORE_STYLE_LABELS.get(selected, selected)
            await query.message.reply_text(
                '⏱️ Gaya dipilih: ' + style_label + '\n\nPilih tempoh video:',
                reply_markup=prompt_duration_menu()
            )
    elif action == 'prompt_style_back' and stage == 'prompt_confirm':
        context.user_data['stage'] = 'prompt_style'
        await query.message.reply_text(
            '🎨 Pilih gaya video sahaja. Semua tetapan lain dipilih automatik.',
            reply_markup=prompt_style_menu(context.user_data.get('prompt_product_type', 'other'))
        )
    elif action == 'prompt_framing_back' and stage == 'prompt_framing':
        context.user_data['stage'] = 'prompt_style'
        await query.message.reply_text('🎨 Pilih gaya video:', reply_markup=prompt_style_menu(context.user_data.get('prompt_product_type', 'other'), context.user_data.get('prompt_model_presence')))
    elif action.startswith('prompt_framing:'):
        selected = action.split(':', 1)[1]
        if selected in PRODUCT_FRAMING and (
            stage == 'prompt_framing'
            or (context.user_data.get('prompt_product_type') and context.user_data.get('prompt_style'))
        ):
            # Accept a valid framing choice from an older Telegram keyboard if the
            # current prompt session still has its product type and visual style.
            context.user_data['prompt_framing'] = selected
            context.user_data['stage'] = 'prompt_ad_angle'
            await query.message.reply_text(
                '🎯 Pilih pendekatan iklan. Pilihan ini akan mengubah cara hook, jalan cerita dan CTA dibina:',
                reply_markup=prompt_ad_angle_menu()
            )
        else:
            logging.warning('Rejected stale prompt framing callback=%r stage=%r', action, stage)
            await query.message.reply_text(
                'Pilihan kamera ini sudah tamat untuk sesi tersebut. Mulakan semula Jana Prompt jika mahu buat prompt baharu.',
                reply_markup=main_menu(update.effective_user.id)
            )
    elif action == 'prompt_idea:yes' and stage == 'prompt_idea_choice':
        context.user_data['prompt_concept'] = ''
        context.user_data['stage'] = 'prompt_scene'
        await query.message.reply_text('🖼️ Pilih latar video:', reply_markup=prompt_scene_menu())
    elif action == 'prompt_idea:skip' and stage == 'prompt_idea_choice':
        context.user_data['prompt_concept'] = ''
        context.user_data['stage'] = 'prompt_scene'
        await query.message.reply_text('🖼️ Pilih latar video:', reply_markup=prompt_scene_menu())
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
            'auto': 'a realistic premium location chosen to suit the product, with natural lighting and believable physical surroundings',
            'studio': 'a premium photography studio with soft neutral backdrop and realistic contact shadows',
            'dark': 'a dark luxury studio with controlled rim lighting and understated premium contrast',
            'home': 'a tasteful modern home interior with natural ambient lighting and believable product placement',
            'nature': 'a restrained natural setting with soft daylight, without obscuring the product',
            'minimal': 'a bright minimalist setting with clean neutral surfaces and soft daylight',
            'kitchen': 'a realistic modern home kitchen, clean counter and softly blurred cabinets',
            'living_room': 'a realistic contemporary living room with sofa, side table and natural window light',
            'office': 'a realistic modern office desk area with neutral workspace and shelves',
            'car_interior': 'inside a realistic clean modern car interior, daylight through windows, product placed naturally and safely',
            'cafe': 'a realistic cozy cafe with wooden tables, warm daylight and softly blurred background',
            'boutique': 'a realistic fashion boutique with clothing racks softly out of focus',
            'mall': 'a realistic modern shopping mall interior with storefronts blurred in the distance',
            'vanity': 'a realistic elegant dressing table and vanity area with mirror and soft natural light',
            'bedroom': 'a realistic neat modern bedroom with bedside table and soft daylight',
            'garden': 'a realistic lush home garden with green plants and soft natural bokeh',
            'beach': 'a realistic tropical beach with sand and sea softly blurred in the distance',
            'gym': 'a realistic modern gym with exercise equipment softly out of focus',
            'library': 'a realistic library with bookshelves softly blurred in the background',
            'workshop': 'a realistic tidy workshop with tools and workbench softly out of focus',
            'bakery': 'a realistic artisan bakery counter with bread displays softly blurred in the background',
            'restaurant': 'a realistic modern restaurant interior with tables and warm ambient lighting',
            'airport': 'a realistic airport lounge with large windows and seating softly out of focus',
            'hotel': 'a realistic premium hotel room with tasteful furniture and natural light'
        }
        selected = action.split(':', 1)[1]
        if selected == 'custom':
            context.user_data['prompt_scene'] = 'use the exact user-supplied background image as the scene/background plate'
            context.user_data['prompt_scene_key'] = 'custom'
            context.user_data['prompt_custom_background'] = True
            context.user_data['stage'] = 'prompt_motion'
            action = 'motion:auto'
        elif selected in scenes:
            context.user_data['prompt_custom_background'] = False
            context.user_data['prompt_scene'] = scenes[selected]
            context.user_data['prompt_scene_key'] = selected
            context.user_data['stage'] = 'prompt_motion'
            action = 'motion:auto'
    # Return only for actions handled by the first chain. Video workflow
    # callbacks must continue into the second chain.
    if action in ('admin_pending', 'admin', 'admin_users_help', 'storyboard', 'make', 'prompt', 'prompt_categories', 'prompt_images_done', 'prompt_style_back') or action.startswith(
        ('admin_approve:', 'admin_reject:', 'admin_users:', 'admin_user:', 'prompt_flow:', 'prompt_mode:', 'prompt_model:', 'prompt_animal_species:', 'prompt_model_count:', 'prompt_model_gender:', 'prompt_model_hijab:', 'prompt_model_ethnicity:', 'prompt_model_age:', 'prompt_language:', 'prompt_voiceover:', 'prompt_type:', 'prompt_product_type:', 'prompt_product_subcategory:', 'prompt_product_categories', 'prompt_duration:',
         'prompt_style:', 'prompt_setup:', 'prompt_ad_angle:', 'prompt_idea:', 'prompt_details:', 'prompt_framing:', 'prompt_text_presence:', 'prompt_text_mode:', 'prompt_audio_presence:', 'prompt_speaker:', 'video_input:', 'prompt_input:', 'pcat:', 'ptpl:')
    ):
        return
    if action.startswith('motion:') and context.user_data.get('stage') == 'prompt_motion':
        motion = action.split(':', 1)[1]
        motions = {'auto': _contextual_motion_instruction(context.user_data.get('prompt_scene_key', 'auto'), context.user_data.get('prompt_product_type', 'other'), context.user_data.get('prompt_model_presence', 'yes')), 'orbit': 'A controlled 30-degree camera arc around the product, not a full 360-degree rotation; preserve the visible product geometry.', 'push': 'A slow forward camera push-in toward the product to reveal texture and details; avoid digital warping and preserve product geometry.', 'pull': 'A slow camera pull-back away from the product to reveal its full shape and surrounding scene; preserve proportions.', 'side': 'A smooth horizontal left-to-right camera slide with stable product proportions.', 'dolly': 'A slow physical-feeling forward dolly-in with gentle natural parallax; no object deformation.', 'low': 'A restrained low-angle camera view looking slightly upward at the product; preserve the reference design and proportions.', 'static': 'A locked camera with subtle studio lighting changes only; keep the product clear and stable.'}
        if motion in motions:
            context.user_data['prompt_motion_choice'] = motion
            context.user_data['stage'] = 'prompt_confirm'
            style_key = context.user_data.get('prompt_style', 'auto')
            style_labels = dict(storyboard_styles())
            style_name = 'Auto (Disyorkan)' if style_key == 'auto' else style_labels.get(style_key, style_key)
            concept = context.user_data.get('prompt_concept', '').strip() or 'Tiada'
            product_name = context.user_data.get('prompt_product_name', '').strip() or 'Tidak diisi'
            scene = context.user_data.get('prompt_scene', 'clean studio background')
            scene_labels = {
                'clean premium studio background, selected to complement the exact product reference': 'Auto — studio premium',
                'premium photography studio, soft neutral backdrop and realistic contact shadows': 'Studio Premium',
                'dark luxury studio, controlled rim lighting and understated premium contrast': 'Mewah Gelap',
                'tasteful modern home interior, natural ambient lighting and believable product placement': 'Ruang Rumah',
                'restrained natural setting with soft daylight, without obscuring the product': 'Alam Semula Jadi',
                'bright minimalist setting with clean neutral surfaces and soft daylight': 'Cerah Minimalis',
                'use the exact user-supplied background image as the scene/background plate': 'Latar sendiri (wajib upload imej latar ke AI)',
            }
            gender_labels = {'female': 'Wanita', 'male': 'Lelaki'}
            ethnicity_labels = {'Malay': 'Melayu', 'Chinese': 'Cina', 'Indian': 'India', 'random_malaysia': 'Rawak'}
            hijab_labels = {'hijab': 'Bertudung', 'no_hijab': 'Tidak bertudung', 'na': 'Tidak berkenaan'}
            category_summary = context.user_data.get('prompt_custom_category_name') or PRODUCT_TYPES.get(context.user_data.get('prompt_product_type', 'other'), 'Produk lain')
            subcategory_summary = context.user_data.get('prompt_custom_subcategory_name') or PRODUCT_SUBTYPE_LABELS.get(context.user_data.get('prompt_product_subcategory', ''), 'Tidak dinyatakan')
            if context.user_data.get('prompt_model_presence') != 'yes':
                model_summary = 'Tiada — fokus produk'
            else:
                gender1 = gender_labels.get(context.user_data.get('prompt_model_gender', 'female'), 'Tidak dinyatakan')
                hijab1 = hijab_labels.get(context.user_data.get('prompt_model_hijab', 'na'), 'Tidak dinyatakan')
                ethnicity1 = ethnicity_labels.get(context.user_data.get('prompt_model_ethnicity', 'random_malaysia'), 'Rawak')
                model_summary = f"{context.user_data.get('prompt_model_count', 1)} model; Model 1: {gender1}, {ethnicity1}, umur {context.user_data.get('prompt_model_age', '26-40')}, {hijab1}"
                if int(context.user_data.get('prompt_model_count', 1)) == 2:
                    gender2 = gender_labels.get(context.user_data.get('prompt_model_gender_2', 'male'), 'Tidak dinyatakan')
                    hijab2 = hijab_labels.get(context.user_data.get('prompt_model_hijab_2', 'na'), 'Tidak berkenaan')
                    ethnicity2 = ethnicity_labels.get(context.user_data.get('prompt_model_ethnicity_2', 'random_malaysia'), 'Rawak')
                    model_summary += f"; Model 2: {gender2}, {ethnicity2}, umur {context.user_data.get('prompt_model_age_2', '26-40')}, {hijab2}"
            summary = chr(10).join([
                '🧾 SEMAK PILIHAN SEBELUM JANA PROMPT',
                '',
                f'🛍️ Nama produk: {product_name}',
                f'📦 Kategori: {category_summary}',
                f'🔎 Subkategori: {subcategory_summary}',
                f'⏱️ Tempoh: {context.user_data.get("prompt_duration", 10)} saat — ' + ('satu prompt' if context.user_data.get('prompt_duration_mode', 'split' if context.user_data.get('prompt_duration') == 20 else 'single') == 'single' else str(int(context.user_data.get('prompt_duration', 10)) // 10) + ' prompt bersambung 10 saat'),
                f'👤 Model: {model_summary}',
                f'🎨 Gaya video: {style_name}',
                '🎥 Gaya kamera: ' + PRODUCT_FRAMING.get(context.user_data.get('prompt_framing','auto'), PRODUCT_FRAMING['auto'])[0],
                '🎯 Pendekatan iklan: ' + {'auto':'Auto — ikut produk','question':'Hook soalan','reveal':'Reveal produk','demo':'Demonstrasi','relatable':'Situasi harian','premium':'Premium / editorial','affiliate':'Promoter affiliate'}.get(context.user_data.get('prompt_ad_angle','auto'),'Auto — ikut produk'),
                '📝 Teks skrin: ' + ('Tiada' if context.user_data.get('prompt_on_screen_text') != 'yes' else ('Auto' if context.user_data.get('prompt_text_mode') == 'auto' else context.user_data.get('prompt_text_content','Manual'))),
                '🔊 Suara: ' + ('Tiada' if not context.user_data.get('prompt_audio_enabled') else str(context.user_data.get('prompt_speech_source','voiceover')) + ' / ' + str(context.user_data.get('prompt_voiceover_style','auto'))),
                f'🖼️ Latar: {scene_labels.get(scene, scene)}',
                '🎥 Aksi & rakaman: Automatik mengikut produk dan latar',
                '',
                'Semak semua pilihan di atas. Tekan Jana Prompt untuk meneruskan.'
            ])
            await query.message.reply_text(summary, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✅ Jana Prompt', callback_data='prompt_generate:confirm')],
                [InlineKeyboardButton('🔁 Mula Semula / Tukar Pilihan', callback_data='prompt')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
            ]))
    elif action == 'prompt_chatgpt_storyboard':
        access = await prompt_access_status(update.effective_user.id)
        if not access["available"]:
            await query.message.reply_text("⚠️ Sistem trial belum dapat disemak. Sila cuba lagi kemudian.")
            return
        if not access["allowed"]:
            await query.message.reply_text(
                "🎁 Anda telah menggunakan 3/3 trial Jana Prompt. Langgan Klippo untuk meneruskan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 Lihat Langganan", callback_data="subscription")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="home")],
                ])
            )
            return
        duration = int(context.user_data.get('prompt_duration', 10))
        image_ids = context.user_data.get('prompt_reference_photos', [])
        if not image_ids:
            await query.message.reply_text('⚠️ Tiada gambar rujukan ditemui. Sila mulakan prompt baharu dan hantar gambar produk.')
            return
        context.user_data["_prompt_trial_count_on_success"] = not access["active"]
        context.user_data["busy"] = True
        waiting = await query.message.reply_text('⏳ GEMINI STORYBOARD — 0%\nMenghantar gambar rujukan dan menyediakan babak...')
        try:
            images = []
            for file_id in image_ids[:4]:
                telegram_file = await context.bot.get_file(file_id)
                image_bytes = bytes(await telegram_file.download_as_bytearray())
                if image_bytes:
                    images.append(image_bytes)
            if not images:
                raise RuntimeError('Gambar rujukan tidak dapat dimuat turun daripada Telegram.')
            language = context.user_data.get('prompt_language', 'Malay')
            language_label = {'Malay': 'Bahasa Melayu', 'English': 'English', 'none': 'Bahasa Melayu untuk penerangan; jangan cadangkan teks pada skrin'}.get(language, 'Bahasa Melayu')
            voiceover_mode = context.user_data.get('prompt_voiceover_mode', 'none')
            voiceover = context.user_data.get('prompt_voiceover_script', '').strip()
            if voiceover_mode == 'script' and voiceover:
                voiceover_instruction = 'Gunakan skrip dialog/voiceover pengguna ini tepat tanpa mengubahnya: ' + voiceover
            elif voiceover_mode == 'ai':
                voice_style_label = {'cute': 'comel dan ceria tetapi tidak dibuat-buat', 'serious': 'serius, tenang dan profesional', 'energetic': 'bertenaga dan teruja tanpa menjerit', 'friendly': 'mesra dan bersahaja seperti rakan yang membantu', 'soft': 'lembut dan menenangkan tetapi tetap jelas', 'ai': 'natural dan santai'}.get(context.user_data.get('prompt_voiceover_style', 'ai'), 'natural dan santai')
                voiceover_instruction = 'Cadangkan dialog/voiceover ringkas dalam ' + language_label + '. Gaya suara: ' + voice_style_label + '. Jika Bahasa Melayu, gunakan sebutan Bahasa Melayu Malaysia yang jelas, kosa kata Malaysia dan intonasi semula jadi; jangan gunakan slang, kosa kata, loghat atau intonasi Indonesia. Sesuaikan emosi dan kelajuan suara dengan produk, pastikan setiap ayat muat dalam durasi babak. Muzik latar tidak boleh menenggelamkan suara.'
            else:
                voiceover_instruction = 'Dialog tidak wajib. Utamakan penceritaan visual; nyatakan “Tanpa dialog” jika dialog tidak diperlukan.'
            model_instruction = prompt_creative_settings(context.user_data)
            prompt_instruction = (
                'Anda ialah pengarah kreatif iklan produk. Analisis SEMUA gambar rujukan yang dilampirkan dan hasilkan storyboard video produk yang boleh terus digunakan sebagai arahan penjana video AI. '
                'Tulis hasil dalam ' + language_label + '. Durasi tepat ' + str(duration) + ' saat, format menegak 9:16. '
                + ('Bina ' + str(4 if duration <= 10 else (6 if duration <= 15 else 8)) + ' babak, setiap babak kira-kira ' + str(round(duration / (4 if duration <= 10 else (6 if duration <= 15 else 8)), 2)) + ' saat. ' + ('Pastikan keempat-empat babak membentuk aliran lengkap.' if duration <= 10 else ('Babak 5–6 mesti menyambung secara visual daripada babak 1–4.' if duration <= 15 else 'Babak 5–8 mesti bersambung secara visual daripada babak 1–4.')))
                + ' Untuk setiap babak, nyatakan masa tepat, tujuan babak, saiz shot, sudut kamera, satu aksi utama, gerakan kamera, komposisi produk, pencahayaan/latar, suara latar atau “Tanpa dialog”, dan peralihan. Arahan mesti khusus dan boleh dilaksanakan, bukan kata umum seperti “cinematic” sahaja. '
                'Kekalkan identiti produk tepat seperti gambar: bentuk, warna, nisbah, logo asal dan aksesori yang kelihatan. Jangan reka bahagian tersembunyi, bahan, ciri, prestasi, harga, promosi atau dakwaan yang tidak disahkan. Jika butiran tidak kelihatan, jangan mereka-rekanya. '
                'Kekalkan identiti dan lingkungan umur model yang dipilih pada semua babak. Jangan ubah umur, identiti atau rupa model antara babak. Jangan tambah teks pada skrin, sari kata, logo tambahan atau watermark. '
                'STRUKTUR IKLAN WAJIB: sediakan HOOK pada 0–2 saat yang khusus kepada produk dan menarik perhatian tanpa dakwaan rekaan; bahagian tengah yang menunjukkan produk, butiran yang benar-benar kelihatan dan/atau demonstrasi yang munasabah; serta CTA yang jelas pada babak akhir. CTA boleh mengajak penonton menyemak butiran produk atau melihat pilihan yang tersedia, tetapi jangan mereka harga, diskaun, stok, pautan atau jaminan. Hook dan CTA mesti dinyatakan secara khusus dalam storyboard. '
                'Jika mod suara AI dipilih, masukkan ayat hook dalam babak pertama dan ayat CTA dalam babak terakhir. Gunakan Bahasa Melayu Malaysia yang semula jadi, jelas dan ringkas, serta pastikan dialog muat dalam tempoh babak. Jika pengguna memilih tanpa dialog, tandakan “Tanpa dialog” dan sampaikan hook/CTA melalui aksi visual, bukan teks pada skrin. Jangan ulang ayat klise yang sama untuk semua produk. '
                'Rancang jalan cerita khusus mengikut kategori produk: hook visual pada awal, paparan penuh, butiran yang benar-benar kelihatan, konteks penggunaan yang munasabah jika sesuai, dan penutup yang menyokong CTA. Setiap babak mesti mempunyai satu aksi utama yang jelas dan berbeza serta paling banyak satu gerakan kamera yang terkawal. Pastikan model, tangan, sentuhan objek, perspektif, pantulan, bayang sentuhan, pencahayaan dan fokus realistik serta konsisten; elakkan perubahan bentuk produk, objek terapung, anggota tambahan, objek berganda, kelipan, jitter, pendedahan cahaya melompat, gerakan mustahil dan potongan mengejut. Gunakan peralihan yang bermotivasi dan lancar, komposisi kemas, produk sentiasa jelas, serta bingkai akhir hero yang stabil. Jika gaya doodle dipilih, selaraskan bunyi lukisan/whoosh lembut dengan garisan bergerak, chime halus pada sorotan dan pop lembut apabila bulatan muncul; bunyi mesti ringkas, tepat pada masa, tidak bertindih dan lebih perlahan daripada suara. Untuk aksi lain, gunakan SFX semula jadi hanya apabila aksi itu benar-benar kelihatan; jangan mereka bunyi fungsi produk. Muzik latar menyokong video dan tidak menenggelamkan suara. Jika penjana tidak menyokong audio, jangan dakwa SFX pasti terhasil. '
                + voiceover_instruction + '\n\nPILIHAN PENGGUNA:\n' + model_instruction
                + '\n\nFORMAT OUTPUT WAJIB: 1) Tajuk dan konsep. 2) HOOK: ayat pembukaan dan aksi visual. 3) STORYBOARD: babak bernombor dengan masa tepat, tujuan, visual/aksi, saiz dan sudut shot, gerakan kamera, pencahayaan/latar, suara latar atau “Tanpa dialog”, dan peralihan. 4) CTA: ayat penutup dan aksi visual. 5) SEMAKAN KUALITI: kesinambungan produk, fakta tidak direka, dialog muat dalam durasi, tiada teks/logo tambahan. Hasilkan storyboard teks sahaja; jangan hasilkan imej storyboard atau prompt video penuh dahulu.'
            )
            context.user_data['prompt_storyboard_fallback'] = prompt_instruction
            await progress_update(waiting, 35, 'Klippo sedang menjana storyboard secara automatik...')
            storyboard = await generate_storyboard(images, prompt_instruction)
            if not storyboard:
                raise RuntimeError('Gemini tidak memulangkan storyboard.')
            context.user_data['stage'] = 'prompt_storyboard_ready'
            storyboard_actions = InlineKeyboardMarkup([
                [InlineKeyboardButton('➡️ Jana Prompt Video Klippo', callback_data='prompt_continue_video')],
                [InlineKeyboardButton('🔁 Jana Storyboard Baharu', callback_data='prompt_chatgpt_storyboard')],
                [InlineKeyboardButton('🏠 Menu Utama', callback_data='home')]
            ])
            await progress_update(waiting, 85, 'Mengemas dan menghantar storyboard teks...')
            await query.message.reply_text(
                '🎬 STORYBOARD TEKS SIAP\n\n'
                'Storyboard ini mengandungi urutan babak, masa, arahan visual, gerakan kamera, kesinambungan produk dan cadangan suara latar. '
                'Tiada imej storyboard dijana; gunakan gambar produk asal apabila menghantar prompt ke platform video AI.',
                reply_markup=storyboard_actions
            )
            if len(storyboard) <= 3900:
                await query.message.reply_text(storyboard, reply_markup=storyboard_actions)
            else:
                storyboard_file = BytesIO(storyboard.encode('utf-8'))
                storyboard_file.name = 'KLIPPO_STORYBOARD_TEKST.txt'
                await query.message.reply_document(
                    document=storyboard_file,
                    filename=storyboard_file.name,
                    caption='📋 Storyboard teks lengkap mengikut babak.',
                    reply_markup=storyboard_actions
                )
            await record_prompt_trial_success(context, update.effective_user.id)
            await progress_update(waiting, 100, 'Storyboard Klippo selesai.')
        except Exception as exc:
            context.user_data["_prompt_trial_count_on_success"] = False
            logging.exception('Automatic storyboard generation failed')
            message = str(exc)[:260]
            fallback_prompt = context.user_data.get('prompt_storyboard_fallback', '').strip()
            if not fallback_prompt:
                fallback_prompt = (
                    'Bertindak sebagai pengarah kreatif iklan produk. Analisis gambar produk yang saya lampirkan dan hasilkan storyboard video menegak 9:16 selama '
                    + str(duration) + ' saat. Pecahkan kepada babak 2 saat setiap satu. Untuk setiap babak nyatakan masa, aksi visual khusus, framing/pergerakan kamera, kesinambungan dan peralihan. Kekalkan produk tepat seperti gambar; jangan reka warna, logo, ciri atau dakwaan yang tidak kelihatan. Jangan tambah teks pada skrin, sari kata, logo tambahan atau watermark. Mulakan dengan hook visual kuat dan tamat dengan product hero shot. Hasilkan storyboard sahaja, bukan prompt video penuh.'
                )
            await query.message.reply_text(
                '⚠️ Klippo tidak dapat menjana storyboard secara automatik kali ini. Anda tidak perlu pilih alternatif jika automatik berjaya.\n\n'
                'Butiran ralat: ' + message + '\n\n'
                'Pilih servis AI di bawah, kemudian gunakan prompt yang Klippo sediakan dalam mesej seterusnya bersama gambar produk.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('🤖 Buka ChatGPT', url='https://chatgpt.com/'),
                     InlineKeyboardButton('✨ Buka Gemini', url='https://gemini.google.com/')],
                    [InlineKeyboardButton('🪄 Buka Microsoft Copilot', url='https://copilot.microsoft.com/')],
                    [InlineKeyboardButton('🔁 Cuba Jana Automatik Lagi', callback_data='prompt_chatgpt_storyboard')],
                    [InlineKeyboardButton('🏠 Menu Utama', callback_data='home')]
                ])
            )
            if len(fallback_prompt) <= 3900:
                await query.message.reply_text(
                    '📋 PROMPT ALTERNATIF — JANA STORYBOARD\n\n'
                    'Salin prompt ini dan tampal di ChatGPT, Gemini atau Copilot. Lampirkan gambar produk yang sama.\n\n'
                    + fallback_prompt,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton('🤖 ChatGPT', url='https://chatgpt.com/'),
                         InlineKeyboardButton('✨ Gemini', url='https://gemini.google.com/')]
                    ])
                )
            else:
                prompt_file = BytesIO(fallback_prompt.encode('utf-8'))
                prompt_file.name = 'KLIPPO_PROMPT_ALTERNATIF_STORYBOARD.txt'
                await query.message.reply_document(
                    document=prompt_file,
                    filename=prompt_file.name,
                    caption='📋 Prompt alternatif storyboard. Lampirkan gambar produk apabila menggunakan prompt ini.'
                )
        finally:
            context.user_data["busy"] = False
            try:
                await waiting.delete()
            except Exception:
                pass
    elif action in ('prompt_caption_generate', 'prompt_caption_copy'):
        product_name = str(context.user_data.get('prompt_product_name') or context.user_data.get('prompt_product') or '').strip()
        if not product_name:
            await query.message.reply_text('⚠️ Nama produk tidak ditemui. Sila jana prompt video dahulu.')
            return
        product_type = str(context.user_data.get('prompt_product_type') or context.user_data.get('prompt_detected_category') or 'other')
        custom_category = str(context.user_data.get('prompt_custom_category_name') or '').strip()
        category = custom_category or product_type
        subcategory = str(context.user_data.get('prompt_custom_subcategory_name') or context.user_data.get('prompt_product_subcategory') or '').strip()
        caption_text = context.user_data.get('prompt_caption_ready', '')
        if action == 'prompt_caption_generate' or not caption_text:
            caption_text = generate_caption(product_name, category, subcategory, 'Shopee')
            context.user_data['prompt_caption_ready'] = caption_text
        if action == 'prompt_caption_copy':
            await query.message.reply_text(caption_text)
        else:
            await query.message.reply_text(
                caption_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📋 Papar untuk Disalin', callback_data='prompt_caption_copy')],
                    [InlineKeyboardButton('🔁 Jana Caption Baharu', callback_data='prompt_caption_generate')],
                    [InlineKeyboardButton('↩️ Kembali ke Prompt Video', callback_data='prompt_continue_video')]
                ])
            )
    elif action == 'prompt_continue_video':
        prompt = context.user_data.get('prompt_video_ready', '')
        if not prompt:
            await query.message.reply_text('⚠️ Prompt video belum tersedia. Sila jana prompt semula.', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🎬 Jana Prompt Semula', callback_data='prompt')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
            ]))
        else:
            context.user_data['stage'] = 'prompt_video_ready'
            sections = re.split(r'\n\n=== KLIPPO PART [2-3] ===\n\n', prompt) if context.user_data.get('prompt_duration_mode', 'split' if context.user_data.get('prompt_duration') == 20 else 'single') == 'split' else [prompt]
            video_actions = InlineKeyboardMarkup([
                [InlineKeyboardButton('🌐 Google Flow / Veo', url='https://labs.google/fx/tools/flow'),
                 InlineKeyboardButton('🎬 Kling AI', url='https://kling.ai/')],
                [InlineKeyboardButton('🤖 NexaBot', url='https://t.me/aigeneratornexa_bot?start=ref37141287'),
                 InlineKeyboardButton('🌐 AxcelStudio', url='https://axcel.cloud/a/3839266034')],
                [InlineKeyboardButton('✨ Gemini', url='https://gemini.google.com/')],
                [InlineKeyboardButton('✍️ Jana Caption + Hashtag', callback_data='prompt_caption_generate')],
                [InlineKeyboardButton('✍️ Prompt Baharu', callback_data='prompt'),
                 InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
            ])
            if context.user_data.get('prompt_mode') == 'storyboard':
                video_intro = (
                    '🎬 PROMPT VIDEO —  PILIHAN\n\n'
                    'Storyboard telah dijana dahulu. Muat naik gambar produk asal yang sama sebagai rujukan, kemudian salin prompt video di bawah.\n'
                    'Untuk klip bersambung, jana setiap bahagian mengikut turutan dan gunakan bingkai akhir bahagian sebelumnya sebagai rujukan bahagian seterusnya.'
                )
            else:
                video_intro = (
                    '🎬  2 — PROMPT VIDEO\n\n'
                    '1. Muat naik imej yang dijana dalam  1 ke platform AI pilihan.\n'
                    '2. Salin prompt video di bawah dan tampal pada platform tersebut.\n'
                    '3. Jika prompt dibahagikan kepada beberapa klip, jana mengikut turutan dan gunakan bingkai akhir klip sebelumnya sebagai rujukan klip seterusnya.\n\n'
                    'PENTING: Gunakan imej baharu yang dijana daripada PROMPT IMAGE sebagai MASTER reference.'
                )
            await query.message.reply_text(video_intro)
            for index, section in enumerate(sections, 1):
                section = section.strip()
                caption = ('BAHAGIAN ' + str(index) + '/' + str(len(sections)) + ' — jana klip 10 saat secara berasingan. ' +
                           ('Simpan bingkai akhir untuk sambungan bahagian seterusnya.' if index < len(sections) else
                            'Gunakan bingkai akhir bahagian sebelumnya sebagai rujukan kesinambungan.')) if len(sections) > 1 else ''
                # Always send prompts as Telegram text, never as .txt attachments.
                remaining = section
                chunks = []
                while remaining:
                    if len(remaining) <= 3900:
                        chunks.append(remaining)
                        break
                    cut = remaining.rfind('\n', 0, 3900)
                    if cut < 1800:
                        cut = 3900
                    chunks.append(remaining[:cut].rstrip())
                    remaining = remaining[cut:].lstrip()
                for chunk_index, chunk in enumerate(chunks):
                    await query.message.reply_text(
                        chunk,
                        reply_markup=video_actions if chunk_index == len(chunks) - 1 else None
                    )
    elif action == 'prompt_generate_image':
        image_prompt = context.user_data.get('prompt_image_ready', '').strip()
        image_ids = context.user_data.get('prompt_reference_photos', [])
        if not image_prompt or not image_ids:
            await query.message.reply_text(
                '⚠️ Prompt imej atau gambar produk asal tiada. Mulakan prompt baharu dan muat naik gambar produk dahulu.'
            )
            return
        waiting = await query.message.reply_text(
            '⏳ GEMINI IMAGE — 0%\nMenjana satu imej rujukan berdasarkan foto produk asal. Caj API mungkin dikenakan.'
        )
        try:
            telegram_file = await context.bot.get_file(image_ids[0])
            source_bytes = bytes(await telegram_file.download_as_bytearray())
            if not source_bytes:
                raise GeminiProductImageError('Gambar produk tidak dapat dimuat turun daripada Telegram.')
            await progress_update(waiting, 35, 'Gemini sedang mengolah latar dan pencahayaan...')
            generated = await asyncio.to_thread(
                generate_product_reference_image, source_bytes, image_prompt
            )
            image_file = BytesIO(generated)
            image_file.name = 'KLIPPO_GEMINI_PRODUCT_REFERENCE.png'
            await query.message.reply_photo(
                photo=image_file,
                caption='🖼️ IMEJ RUJUKAN PRODUK SIAP\nGunakan imej ini bersama prompt video. Semak dahulu bahawa warna, bentuk, corak dan logo produk kekal tepat seperti foto asal.'
            )
            await progress_update(waiting, 100, 'Imej rujukan siap.')
        except GeminiProductImageError as exc:
            await query.message.reply_text('⚠️ Imej tidak berjaya dijana. ' + str(exc))
        except Exception:
            logging.exception('Gemini product image generation failed')
            await query.message.reply_text('⚠️ Imej tidak berjaya dijana kali ini. Prompt asal masih tersedia; cuba lagi kemudian.')
        finally:
            try:
                await waiting.delete()
            except Exception:
                pass
    elif action == 'prompt_generate:confirm' and context.user_data.get('stage') == 'prompt_confirm':
        access = await prompt_access_status(update.effective_user.id)
        if not access["available"]:
            await query.message.reply_text("⚠️ Sistem trial belum dapat disemak. Prompt belum dijana; sila cuba lagi.")
            return
        if not access["allowed"]:
            await query.message.reply_text(
                "🎁 Anda telah menggunakan 3/3 trial Jana Prompt. Langgan Klippo untuk meneruskan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 Lihat Langganan", callback_data="subscription")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="home")],
                ])
            )
            return
        context.user_data["_prompt_trial_count_on_success"] = not access["active"]
        motion = context.user_data.get('prompt_motion_choice', 'push')
        motions = {'auto': _contextual_motion_instruction(context.user_data.get('prompt_scene_key', 'auto'), context.user_data.get('prompt_product_type', 'other'), context.user_data.get('prompt_model_presence', 'yes')), 'orbit': 'A controlled 30-degree camera arc around the product, not a full 360-degree rotation; preserve the visible product geometry.', 'push': 'A slow forward camera push-in toward the product to reveal texture and details; avoid digital warping and preserve product geometry.', 'pull': 'A slow camera pull-back away from the product to reveal its full shape and surrounding scene; preserve proportions.', 'side': 'A smooth horizontal left-to-right camera slide with stable product proportions.', 'dolly': 'A slow physical-feeling forward dolly-in with gentle natural parallax; no object deformation.', 'low': 'A restrained low-angle camera view looking slightly upward at the product; preserve the reference design and proportions.', 'static': 'A locked camera with subtle studio lighting changes only; keep the product clear and stable.'}
        if motion in motions:
            context.user_data["busy"] = True
            waiting = await query.message.reply_text('⏳ DALAM PROSES — 0%' + chr(10) + 'Menyusun prompt...')
            try:
                product_name = context.user_data.get('prompt_product_name', '').strip()
                product_parts = ['Product name: ' + product_name, 'Category: ' + (context.user_data.get('prompt_custom_category_name') or PRODUCT_TYPES.get(context.user_data.get('prompt_product_type', 'other'), 'Other'))]
                subtype = context.user_data.get('prompt_custom_subcategory_name') or PRODUCT_SUBTYPE_LABELS.get(context.user_data.get('prompt_product_subcategory', ''), '')
                if subtype:
                    product_parts.append('Subcategory: ' + subtype)
                optional_details = str(context.user_data.get('prompt_product', '') or '').strip()
                if optional_details:
                    product_parts.append('Product details: ' + optional_details)
                product = chr(10).join(product_parts)
                scene = context.user_data.get('prompt_scene', 'clean studio background')
                style_choice = context.user_data.get('prompt_style', 'auto')
                # Keep Auto genuinely varied; prompt_engine selects a category/subtype-fit style without immediate repeats.
                prompt = build_prompt(
                    'storyboard', product, scene, motions[motion],
                    style_choice,
                    context.user_data.get('prompt_duration', 10),
                    context.user_data.get('prompt_concept', ''),
                    product_type=context.user_data.get('prompt_product_type', 'other'),
                    storyboard_override=context.user_data.get('prompt_library_storyboard') or None,
                    split=context.user_data.get('prompt_duration_mode', 'split' if context.user_data.get('prompt_duration') == 20 else 'single') == 'split',
                    universal_custom=bool(
                        context.user_data.get('prompt_custom_category_name')
                        or context.user_data.get('prompt_custom_subcategory_name')
                    ),
                    product_subtype=context.user_data.get('prompt_product_subcategory', ''),
                    prompt_language=context.user_data.get('prompt_language', 'Malay')
                )
                component_rules = _prompt_library_component_rules(
                    context.user_data.get('prompt_library_id'),
                    audio_enabled=context.user_data.get('prompt_audio_enabled', True) is not False,
                    voiceover_mode=context.user_data.get('prompt_voiceover_mode', 'none'),
                    prompt_language=context.user_data.get('prompt_language', 'Malay'),
                    on_screen_text=context.user_data.get('prompt_on_screen_text', 'no'),
                    camera_choice=motion,
                )
                if component_rules:
                    prompt = prompt.rstrip() + '\n\nREUSABLE COMPONENT RULES:\n' + component_rules
                if context.user_data.get('prompt_model_presence') == 'yes' and int(context.user_data.get('prompt_model_count',1)) == 2:
                    prompt += ('\n\nTWO-MODEL CAST: Model 1 is ' + str(context.user_data.get('prompt_model_gender','female')) + ', appearance ' + str(context.user_data.get('prompt_model_ethnicity','random_malaysia')) + ', age ' + str(context.user_data.get('prompt_model_age','26-40')) + ', hijab ' + str(context.user_data.get('prompt_model_hijab','na')) + '. Model 2 is ' + str(context.user_data.get('prompt_model_gender_2','male')) + ', appearance ' + str(context.user_data.get('prompt_model_ethnicity_2','random_malaysia')) + ', age ' + str(context.user_data.get('prompt_model_age_2','26-40')) + ', hijab ' + str(context.user_data.get('prompt_model_hijab_2','na')) + '. Keep identities distinct and consistent.')
                # Text and audio options are added once by prompt_creative_settings below.
                framing_key = context.user_data.get('prompt_framing', 'auto')
                # Always tailor actions to the actual product and its intended age group.
                if _prompt_is_child_product(context.user_data):
                    selected_category = context.user_data.get('prompt_product_type', 'other')
                    selected_subcategory = str(context.user_data.get('prompt_product_subcategory', '')).lower()
                    selected_age = str(context.user_data.get('prompt_model_age', '26-40'))
                    if selected_category == 'baby' or selected_subcategory.startswith('baby_'):
                        age_action_rule = 'BABY PRODUCT: show one safe, supervised, age-appropriate interaction; do not invent features or unsafe use.'
                    elif selected_age in {'4-7', '8-12', '13-17'} and context.user_data.get('prompt_model_presence') == 'yes':
                        age_action_rule = 'CHILD ACTION: one natural, age-appropriate action suited to this product; keep it visible and unchanged.'
                    else:
                        age_action_rule = 'CHILD-SIZED PRODUCT: present it on a suitable hanger or surface; do not imply an adult is the wearer.'
                    prompt = prompt.rstrip() + '\n' + age_action_rule
                if framing_key != 'auto':
                    framing = PRODUCT_FRAMING.get(framing_key)
                    if framing:
                        # Keep the selected framing's core direction; the generated storyboard
                        # already supplies timing, camera and product-continuity rules.
                        framing_direction = ' '.join(str(framing[1]).split()).strip()
                        prompt = prompt.rstrip() + '\nCAMERA FRAMING: ' + framing_direction.rstrip('. ') + '.'
                prompt = prompt.rstrip() + '\n\n' + prompt_creative_settings(context.user_data)
                if framing_key == 'product_only':
                    prompt += '\nPRODUCT-ONLY PRIORITY: This selected framing overrides conflicting style or action suggestions. Show no person, hands, face, body parts or animal; use camera movement only and keep the exact product fully visible.'
                await progress_update(waiting, 70, 'Menyediakan PROMPT IMAGE dan PROMPT VIDEO...')
                context.user_data['stage'] = 'prompt_done'
                mode_name = context.user_data.get('prompt_mode', 'normal')
                # Keep the existing premium video prompt and show it only after the user
                # has used the image prompt, so the workflow is clearly image -> video.
                context.user_data['prompt_video_ready'] = prompt
                if mode_name == 'storyboard':
                    # Storyboard mode must start with the storyboard itself, not an image-prompt step.
                    duration = int(context.user_data.get('prompt_duration', 10))
                    image_ids = context.user_data.get('prompt_reference_photos', [])
                    if not image_ids:
                        raise RuntimeError('Tiada gambar rujukan. Sila mulakan semula dan hantar gambar produk.')
                    await progress_update(waiting, 25, 'Menyediakan gambar rujukan untuk storyboard...')
                    images = []
                    for file_id in image_ids[:4]:
                        telegram_file = await context.bot.get_file(file_id)
                        image_bytes = bytes(await telegram_file.download_as_bytearray())
                        if image_bytes:
                            images.append(image_bytes)
                    if not images:
                        raise RuntimeError('Gambar rujukan tidak dapat dimuat turun daripada Telegram.')
                    language = context.user_data.get('prompt_language', 'Malay')
                    language_label = {'Malay': 'Bahasa Melayu', 'English': 'English', 'none': 'Bahasa Melayu untuk penerangan; jangan cadangkan teks pada skrin'}.get(language, 'Bahasa Melayu')
                    voiceover_mode = context.user_data.get('prompt_voiceover_mode', 'none')
                    voiceover = context.user_data.get('prompt_voiceover_script', '').strip()
                    if voiceover_mode == 'script' and voiceover:
                        voiceover_instruction = 'Gunakan skrip dialog/voiceover pengguna ini tepat tanpa mengubahnya: ' + voiceover
                    elif voiceover_mode == 'ai':
                        voice_style_label = {'cute': 'comel dan ceria tetapi tidak dibuat-buat', 'serious': 'serius, tenang dan profesional', 'energetic': 'bertenaga dan teruja tanpa menjerit', 'friendly': 'mesra dan bersahaja seperti rakan yang membantu', 'soft': 'lembut dan menenangkan tetapi tetap jelas', 'ai': 'natural dan santai'}.get(context.user_data.get('prompt_voiceover_style', 'ai'), 'natural dan santai')
                        voiceover_instruction = 'Cadangkan dialog/voiceover ringkas dalam ' + language_label + '. Gaya suara: ' + voice_style_label + '. Jika Bahasa Melayu, gunakan sebutan Bahasa Melayu Malaysia yang jelas, kosa kata Malaysia dan intonasi semula jadi; jangan gunakan slang, kosa kata, loghat atau intonasi Indonesia. Sesuaikan emosi dan kelajuan suara dengan produk, pastikan setiap ayat muat dalam durasi babak. Muzik latar tidak boleh menenggelamkan suara.'
                    else:
                        voiceover_instruction = 'Dialog tidak wajib. Utamakan penceritaan visual; nyatakan “Tanpa dialog” jika dialog tidak diperlukan.'
                    model_instruction = prompt_creative_settings(context.user_data)
                    prompt_instruction = (
                        'Anda ialah pengarah kreatif iklan produk. Analisis gambar rujukan yang dilampirkan dan hasilkan storyboard video produk yang boleh terus digunakan sebagai arahan penjana video AI. '
                        'Tulis hasil dalam ' + language_label + '. Durasi tepat ' + str(duration) + ' saat, format menegak 9:16. '
                        + ('Bina 4 babak berturutan dalam satu helaian storyboard.' if duration <= 10 else 'Bina 8 babak berturutan dalam dua helaian storyboard; babak 5–8 mesti bersambung daripada babak 1–4.')
                        + ' Untuk setiap babak, nyatakan masa tepat, tujuan, saiz dan sudut shot, satu aksi utama, gerakan kamera, komposisi produk, pencahayaan/latar, suara latar pilihan yang muat dalam tempoh, serta peralihan yang menyambungkan babak. Arahan mesti khusus dan boleh dilaksanakan, bukan kata umum sahaja. '
                        'Kekalkan bentuk, warna, nisbah, logo asal dan aksesori yang kelihatan. Jangan reka bahagian tersembunyi, bahan, ciri, prestasi, harga atau dakwaan. Pastikan tangan, model dan interaksi realistik. Jangan tambah teks pada skrin, sari kata, label, logo tambahan atau watermark. '
                        + voiceover_instruction + '\n\nPILIHAN PENGGUNA:\n' + model_instruction
                        + '\n\nFormat output: tajuk ringkas, konsep, kemudian senarai babak bernombor. Jangan hasilkan prompt video penuh dahulu.'
                    )
                    await progress_update(waiting, 40, 'Menjana storyboard...')
                    storyboard = await generate_storyboard(images, prompt_instruction)
                    if not storyboard:
                        raise RuntimeError('Gemini tidak memulangkan storyboard.')
                    context.user_data['stage'] = 'prompt_storyboard_ready'
                    storyboard_actions = InlineKeyboardMarkup([
                        [InlineKeyboardButton('➡️ Jana Prompt Video Klippo', callback_data='prompt_continue_video')],
                        [InlineKeyboardButton('🔁 Jana Storyboard Baharu', callback_data='prompt_chatgpt_storyboard')],
                        [InlineKeyboardButton('🏠 Menu Utama', callback_data='home')]
                    ])
                    scene_count = 4 if duration <= 10 else 8
                    sheet_count = (scene_count + 3) // 4
                    visual_error = None
                    await progress_update(waiting, 65, 'Menjana helaian storyboard bergambar...')
                    for sheet_number in range(1, sheet_count + 1):
                        try:
                            sheet_bytes = await asyncio.to_thread(
                                generate_storyboard_sheet, images, storyboard, duration, sheet_number, language_label
                            )
                            sheet_file = BytesIO(sheet_bytes)
                            sheet_file.name = f'KLIPPO_STORYBOARD_HELAIAN_{sheet_number}.png'
                            await query.message.reply_photo(
                                photo=sheet_file,
                                caption=f'🎬 STORYBOARD BERGAMBAR — HELAIAN {sheet_number}/{sheet_count}\n'
                                        f'Video {duration} saat · Babak {min((sheet_number-1)*4+1, scene_count)}–{min(sheet_number*4, scene_count)}',
                                reply_markup=storyboard_actions if sheet_number == sheet_count else None
                            )
                        except GeminiStoryboardImageError as exc:
                            visual_error = str(exc)
                            logging.warning('Visual storyboard sheet %s failed: %s', sheet_number, type(exc).__name__)
                            break
                        except Exception:
                            visual_error = 'Helaian storyboard bergambar tidak dapat dijana kali ini.'
                            logging.exception('Visual storyboard generation failed')
                            break
                    await query.message.reply_text(
                        ('🎬 STORYBOARD BERGAMBAR SIAP' if not visual_error else '📝 STORYBOARD TEKS SIAP') +
                        '\n\nStoryboard dijana terus berdasarkan gambar produk anda. Prompt video ialah pilihan seterusnya, bukan  wajib sebelum storyboard.',
                        reply_markup=storyboard_actions
                    )
                    if len(storyboard) <= 3900:
                        await query.message.reply_text(storyboard, reply_markup=storyboard_actions)
                    else:
                        storyboard_file = BytesIO(storyboard.encode('utf-8'))
                        storyboard_file.name = 'KLIPPO_STORYBOARD.txt'
                        await query.message.reply_document(document=storyboard_file, filename=storyboard_file.name,
                                                           caption='Penerangan penuh babak storyboard.', reply_markup=storyboard_actions)
                    if visual_error:
                        await query.message.reply_text('⚠️ Helaian bergambar belum tersedia: ' + visual_error)
                    await record_prompt_trial_success(context, update.effective_user.id)
                    await progress_update(waiting, 100, 'Storyboard siap.')
                    return
                if mode_name == 'normal':
                    context.user_data['stage'] = 'prompt_video_ready'
                    sections = re.split(r'\n\n=== KLIPPO PART [2-3] ===\n\n', prompt) if context.user_data.get('prompt_duration_mode', 'split' if context.user_data.get('prompt_duration') == 20 else 'single') == 'split' else [prompt]
                    direct_actions = InlineKeyboardMarkup([
                        [InlineKeyboardButton('🌐 Google Flow / Veo', url='https://labs.google/fx/tools/flow'),
                         InlineKeyboardButton('🎬 Kling AI', url='https://kling.ai/')],
                        [InlineKeyboardButton('🤖 NexaBot', url='https://t.me/aigeneratornexa_bot?start=ref37141287'),
                         InlineKeyboardButton('🌐 AxcelStudio', url='https://axcel.cloud/a/3839266034')],
                        [InlineKeyboardButton('✨ Gemini', url='https://gemini.google.com/')],
                        [InlineKeyboardButton('✍️ Jana Caption + Hashtag', callback_data='prompt_caption_generate')],
                        [InlineKeyboardButton('✍️ Prompt Baharu', callback_data='prompt'),
                         InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
                    ])
                    await query.message.reply_text(
                        '🎥 PROMPT VIDEO TERUS\n\n'
                        + ('🖼️ LATAR SENDIRI DIPILIH\nMuat naik DUA imej ke penjana video: (1) gambar produk asal sebagai rujukan produk, dan (2) gambar latar pilihan anda sebagai rujukan latar. Jika ada tetapan peranan imej, tetapkan imej produk sebagai subjek dan imej latar sebagai latar/scene. Klippo tidak memindahkan fail ke platform luar.\n\n' if context.user_data.get('prompt_custom_background') else '')
                        + 'Muat naik gambar produk asal yang sama ke platform AI pilihan, kemudian salin prompt di bawah. '
                        + ('Klippo tidak menghantar gambar ke laman luar secara automatik. Untuk setiap bahagian video bersambung, muat naik semula gambar produk dan gambar latar yang sama serta gunakan bingkai akhir klip sebelumnya untuk kesinambungan.' if context.user_data.get('prompt_custom_background') else 'Klippo tidak menghantar gambar ke laman luar secara automatik. Untuk video bersambung, muat naik semula gambar produk yang sama dan gunakan bingkai akhir klip sebelumnya untuk kesinambungan.')
                    )
                    for index, section in enumerate(sections, 1):
                        section = section.strip()
                        caption = ('BAHAGIAN ' + str(index) + '/' + str(len(sections)) + ' — jana klip 10 saat secara berasingan. ' +
                                   ('Simpan bingkai akhir untuk sambungan bahagian seterusnya.' if index < len(sections) else
                                    'Gunakan bingkai akhir bahagian sebelumnya sebagai rujukan kesinambungan.')) if len(sections) > 1 else ''
                        # Always send prompts as Telegram text, never as .txt attachments.
                        remaining = section
                        chunks = []
                        while remaining:
                            if len(remaining) <= 3900:
                                chunks.append(remaining)
                                break
                            cut = remaining.rfind('\n', 0, 3900)
                            if cut < 1800:
                                cut = 3900
                            chunks.append(remaining[:cut].rstrip())
                            remaining = remaining[cut:].lstrip()
                        for chunk_index, chunk in enumerate(chunks):
                            await query.message.reply_text(
                                chunk,
                                reply_markup=direct_actions if chunk_index == len(chunks) - 1 else None
                            )
                    await record_prompt_trial_success(context, update.effective_user.id)
                    await progress_update(waiting, 100, 'Prompt video siap.')
                    return
                product_name = context.user_data.get('prompt_product_name', '').strip() or 'product shown in the uploaded reference photo'
                category_label = CATEGORIES_BY_ID.get(context.user_data.get('prompt_category', ''), {}).get('label', 'product')
                selected_background = context.user_data.get(
                    'prompt_scene',
                    'clean premium studio background, selected to complement the exact product reference'
                )
                image_prompt = (
                    'PROMPT IMAGE — PREMIUM PRODUCT CAMPAIGN\n\n'
                    'Use the uploaded product photograph as the sole MASTER product reference. '
                    'Create one ultra-realistic premium commercial product photograph in vertical 9:16. '
                    'The product is: ' + product_name + '. Category: ' + category_label + '.\n\n'
                    'BACKGROUND REPLACEMENT — MANDATORY: Completely remove/replace the original background in the uploaded photo. '
                    'Use this exact user-selected scene as the new background: ' + selected_background + '. '
                    'Do not preserve or recreate the original photo background. Do not place the unchanged source photo on top of a new background. '
                    'Integrate the product naturally into the selected scene with matching perspective, light direction, colour temperature and contact shadows.\n\n'
                    'VISUAL DIRECTION: Create a believable, elegant lifestyle advertising scene suited to this product. '
                    'If a human or animal model was selected, include only that selected model as specified in MODEL DIRECTION below. For clothing, a model may wear the garment only when its age and size are appropriate; otherwise present it on a suitable hanger or surface. If no model was selected, do not add a person or animal. '
                    'If it is a bag, accessory, beauty item, gadget, food or home product, compose a premium scene that showcases the actual item clearly. '
                    'Use soft natural or studio light, realistic shadows, refined composition, authentic textures, and a photographic—not CGI—finish. '
                    'Keep the product prominent and leave enough clear space around it.\n\n'
                    'PRODUCT LOCK: Preserve the exact product identity from the uploaded photo, including its visible shape, colour, print, pattern, cut, packaging, proportions, hardware and details. '
                    'Do not redesign, recolour, replace, add or remove product features. Do not invent logos, labels, accessories, materials or claims. '
                    'For clothing, keep the garment print, neckline, sleeves, fit and fabric appearance faithful to the reference. '
                    'A model or environment may be added only to present the same product; do not let styling obscure it.\n\n'
                    'OUTPUT: One cohesive, photorealistic vertical 9:16 image, premium editorial quality. '
                    'No collage, split screen, poster layout, captions, promotional text, watermark or extra logos. '
                    'Avoid distorted hands, unnatural faces, plastic skin, warped product geometry and artificial CGI appearance.'
                )
                image_prompt += (
                    '\n\nMODEL DIRECTION: ' +
                    image_model_direction(
                        context.user_data,
                        child_product=_prompt_is_child_product(context.user_data),
                    )
                )
                if context.user_data.get('prompt_model_presence') == 'yes':
                    image_prompt += (
                        ' Head covering: ' + str(context.user_data.get('prompt_model_hijab', 'not specified')) +
                        '; appearance: ' + str(context.user_data.get('prompt_model_ethnicity', 'any')) +
                        '. Keep the same face, hair/head covering and outfit consistent throughout.'
                    )
                context.user_data['prompt_image_ready'] = image_prompt
                image_action_rows = [
                    [InlineKeyboardButton('✨ ChatGPT Image', url='https://chatgpt.com/'),
                     InlineKeyboardButton('🌟 Google Gemini', url='https://gemini.google.com/')],
                    [InlineKeyboardButton('🎨 Microsoft Designer', url='https://designer.microsoft.com/')],
                ]
                if context.user_data.get('prompt_mode') == 'storyboard':
                    image_action_rows.append([InlineKeyboardButton('🎬 Jana Storyboard Gemini', callback_data='prompt_chatgpt_storyboard')])
                image_action_rows.extend([
                    [InlineKeyboardButton('➡️ Jana Prompt Video', callback_data='prompt_continue_video')],
                    [InlineKeyboardButton('✍️ Prompt Baharu', callback_data='prompt'),
                     InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
                ])
                image_actions = InlineKeyboardMarkup(image_action_rows)
                await query.message.reply_text(
                    '🖼️  1 — PROMPT IMAGE\n\n'
                    '1. Salin prompt di bawah.\n'
                    '2. Buka salah satu laman AI melalui butang.\n'
                    '3. Muat naik gambar produk asal dan tampal PROMPT IMAGE.\n'
                    '4. Jana imej, kemudian simpan imej yang terhasil.\n\n'
                    'Selepas imej siap, tekan “Jana Prompt Video” untuk mendapatkan prompt video yang menggunakan imej baharu itu sebagai rujukan.',
                    reply_markup=image_actions
                )
                if len(image_prompt) <= 3900:
                    await query.message.reply_text(image_prompt)
                else:
                    image_file = BytesIO(image_prompt.encode('utf-8'))
                    image_file.name = 'KLIPPO_PROMPT_IMAGE.txt'
                    await query.message.reply_document(document=image_file, filename=image_file.name,
                                                       caption='📋 PROMPT IMAGE penuh — buka fail dan salin semua teks.')
                await record_prompt_trial_success(context, update.effective_user.id)
                await progress_update(waiting, 100, 'PROMPT IMAGE siap. Seterusnya jana PROMPT VIDEO.')
            except Exception:
                context.user_data["_prompt_trial_count_on_success"] = False
                logging.exception('Klippo prompt generation failed')
                await query.message.reply_text('❌ Prompt tidak berjaya dijana. Trial tidak ditolak. Sila tekan Jana Prompt sekali lagi. Jika masalah berulang, maklumkan admin Klippo.')
            finally:
                context.user_data["busy"] = False
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
        if choice == 'custom':
            context.user_data['stage'] = 'background_custom_upload'
            await query.message.reply_text('🖼️ Hantar gambar yang mahu digunakan sebagai latar video. Boleh hantar sebagai gambar Telegram atau fail imej JPG, PNG atau WEBP. Gambar ini akan dipadankan dengan saiz video.')
        elif choice in ('original', 'white', 'beige', 'dark', 'pastel', 'navy', 'sage', 'sky', 'lavender', 'rose', 'mint', 'terracotta', 'charcoal', 'gradient', 'pattern', 'duotone', 'mist', 'sky_gradient', 'lavender_gradient', 'sage_gradient', 'blush_gradient', 'midnight_gradient', 'sand_gradient'):
            context.user_data['background'] = choice
            context.user_data.pop('custom_background_file_id', None)
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
            await query.message.reply_text(f"✅ Gaya {context.user_data['style']} dipilih.\n 3/4 — Pilih muzik:", reply_markup=music_menu())
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
        await query.message.reply_text('💎 LANGGANAN KLIPPO\n\nPelan Penyokong Awal: RM2 / 30 hari.\n\nKlippo membantu menyediakan prompt untuk digunakan pada platform video AI pilihan anda, menggerakkan foto dengan transisi, menggabungkan klip dan menukar format video. Penjanaan video AI penuh dibuat pada platform luaran.\n\nBayar melalui QR DuitNow. Selepas pembayaran, hantar resit untuk semakan admin.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'subscription_qr':
        qr_path = Path(__file__).resolve().parent / 'klippo_qr.jpg'
        if not qr_path.is_file():
            await query.message.reply_text('QR pembayaran belum tersedia. Sila cuba lagi kemudian.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
        else:
            with qr_path.open('rb') as qr_file:
                await query.message.reply_photo(photo=qr_file, caption='💎 KLIPPO — DuitNow QR\n\nPelan Penyokong Awal: RM2 / 30 hari. Klippo menyediakan prompt dan alat pemprosesan video; penjanaan video AI penuh dilakukan pada platform luaran.\n\nTekan 📎 Upload Resit selepas pembayaran. Pengaktifan adalah manual selepas semakan.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📎 Upload Resit', callback_data='receipt_upload')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'receipt_upload':
        context.user_data['stage'] = 'receipt_upload'
        await query.message.reply_text('📎 Sila hantar gambar atau fail PDF resit pembayaran di sini.')
    elif action == 'account':
        await account_info(update, context)
    elif action == 'feedback':
        context.user_data['stage'] = 'feedback'
        await query.message.reply_text(
            '💬 KOMEN & CADANGAN KLIPPO\n\n'
            'Taip komen, cadangan atau masalah yang anda temui. Nyatakan  yang dibuat dan hasil yang dijangka jika melaporkan masalah. '
            'Mesej akan dihantar kepada pentadbir Klippo untuk semakan.\n\n'
            'Taip /menu untuk batal dan kembali ke menu utama.'
        )
    elif action == 'help':
        await query.message.reply_text('❓ FAQ KLIPPO\n\nTekan persoalan untuk melihat jawapan dan gambar contoh:', reply_markup=faq_menu())
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
            await query.message.reply_photo(photo=picture, caption=f'❓ {title}\n\n{answer}', reply_markup=keyboard)
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
        # Ignore obsolete or unknown callbacks without sending the stale-menu message.


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stage = context.user_data.get('stage')
    value = update.message.text.strip()
    if value in ('🏠 Menu Utama', 'Menu Utama', 'menu', 'MENU', '/menu'):
        await start(update, context)
        return
    if stage == 'feedback':
        feedback = value[:1800]
        if len(feedback.strip()) < 3:
            await update.message.reply_text('Sila tulis komen atau cadangan yang lebih jelas, atau taip /menu untuk batal.')
            return
        user = update.effective_user
        username = ('@' + user.username) if user.username else '(tiada username)'
        admins = [x.strip() for x in os.environ.get('ADMIN_USER_IDS', '37141287').split(',') if x.strip().isdigit()]
        delivered = False
        for admin_id in admins:
            try:
                await context.bot.send_message(
                    chat_id=int(admin_id),
                    text=(
                        '💬 KOMEN / CADANGAN KLIPPO\n'
                        f'Pengguna: {user.full_name} {username}\n'
                        f'ID Telegram: {user.id}\n\n'
                        f'{feedback}'
                    )
                )
                delivered = True
            except Exception:
                logging.exception('Could not deliver Klippo feedback to admin %s', admin_id)
        context.user_data['stage'] = None
        if delivered:
            await update.message.reply_text('✅ Terima kasih! Komen/cadangan anda telah dihantar kepada pasukan Klippo.', reply_markup=main_menu(user.id))
        else:
            await update.message.reply_text('⚠️ Komen belum dapat dihantar. Cuba lagi kemudian atau hubungi pentadbir.', reply_markup=main_menu(user.id))
        return
    if stage == 'prompt_library_details':
        details = '' if value in ('-', '—', 'tiada', 'Tiada') else value
        context.user_data['prompt_library_details'] = details[:1200]
        if details:
            context.user_data['prompt_product_name'] = details[:240]
            subtype = detect_product_subtype(details)
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
                    '🔎 Klippo mengesan jenis produk: ' + subtype.replace('_', ' ') + '. Pilih prompt khusus dalam koleksi ' + CATEGORIES_BY_ID[category_id].get('label', category_id) + ':',
                    reply_markup=prompt_options_menu(category_id, subtype)
                )
                return
        context.user_data['stage'] = 'prompt_category'
        await update.message.reply_text('📚 Nama produk diterima. Pilih koleksi prompt:', reply_markup=prompt_category_menu())
        return
    if stage == 'prompt_text_content':
        text_content = value.strip()
        if not text_content:
            await update.message.reply_text('Teks tidak boleh kosong. Taip teks yang mahu dipaparkan pada skrin.')
            return
        context.user_data['prompt_text_content'] = text_content[:500]
        context.user_data['stage'] = 'prompt_audio_presence'
        await update.message.reply_text('✅ Teks disimpan. Mahu audio atau suara dalam video?', reply_markup=prompt_audio_presence_menu())
        return
    if stage == 'prompt_voiceover_text':
        script = '' if value.strip() in ('-', '—', 'tiada', 'Tiada') else value.strip()
        context.user_data['prompt_voiceover_script'] = script[:1200]
        if not script:
            context.user_data['prompt_voiceover_mode'] = 'none'
        context.user_data['stage'] = 'prompt_scene'
        await update.message.reply_text('✅ Skrip disimpan.' if script else '✅ Teruskan tanpa dialog.', reply_markup=prompt_scene_menu())
        return
    if stage == 'prompt_custom_category':
        if len(value) < 2 or value.lower().startswith(('http://', 'https://')):
            parent = context.user_data.get('prompt_custom_category_parent', 'category')
            label = 'kategori' if parent == 'category' else 'subkategori'
            await update.message.reply_text(f'⚠️ Taip nama {label} sahaja, bukan pautan. Sekurang-kurangnya 2 aksara.')
            return
        custom_value = ' '.join(value.split())[:100]
        parent = context.user_data.get('prompt_custom_category_parent', 'category')
        if parent == 'category':
            context.user_data['prompt_product_type'] = 'other'
            context.user_data['prompt_custom_category_name'] = custom_value
            context.user_data['prompt_product_subcategory'] = ''
            context.user_data['prompt_custom_subcategory_name'] = ''
            context.user_data['prompt_custom_category_parent'] = 'subcategory'
            context.user_data['stage'] = 'prompt_custom_category'
            await update.message.reply_text(
                f'✅ Kategori sendiri: {custom_value}\n\n📦 Taip subkategori produk. Contoh: aksesori telefon, beg kamera atau serum rambut.'
            )
        else:
            context.user_data['prompt_product_subcategory'] = 'other_other'
            context.user_data['prompt_custom_subcategory_name'] = custom_value
            context.user_data['stage'] = 'prompt_product_name'
            await update.message.reply_text(
                f'✅ Subkategori sendiri: {custom_value}\n\n🛍️ Masukkan nama produk (nama sahaja, bukan pautan):'
            )
        return
    if stage == 'prompt_product_name':
        if len(value) < 2 or value.lower().startswith(('http://', 'https://')):
            await update.message.reply_text('⚠️ Masukkan nama produk sahaja. Buka Shopee, copy nama produk dan paste di sini; pautan tidak diperlukan.')
            return
        context.user_data['prompt_product_name'] = value[:240]
        detected_category = detect_prompt_library_category(value)
        detected_subtype = detect_product_subtype(value)
        bag_subtype = detect_bag_subtype(value)
        selected_subcategory = str(context.user_data.get('prompt_product_subcategory', '') or '')
        explicit_subcategory = selected_subcategory in PRODUCT_SUBTYPE_LABELS
        category_to_product_type = {
            'clothing': 'fashion', 'bags': 'bag', 'wallets': 'wallet',
            'shoes': 'shoes', 'beauty': 'beauty', 'gadgets': 'gadget',
            'home': 'home', 'accessories': 'accessory', 'food': 'food',
            'stationery': 'other', 'sports': 'other', 'travel': 'travel',
            'pets': 'pet', 'automotive': 'automotive', 'garden': 'garden',
            'kitchen': 'kitchen', 'furniture': 'furniture', 'baby': 'baby',
            'crafts': 'crafts',
        }
        if explicit_subcategory:
            selected_category = next(
                (category for category, options in PRODUCT_SUBTYPES.items()
                 if any(slug == selected_subcategory for slug, _label in options)),
                context.user_data.get('prompt_product_type', 'other')
            )
            context.user_data['prompt_product_type'] = selected_category
        else:
            if bag_subtype == 'wallet':
                detected_category = 'wallets'
            elif bag_subtype:
                detected_category = 'bags'
            if detected_category:
                context.user_data['prompt_product_type'] = category_to_product_type.get(detected_category, 'other')
            elif context.user_data.get('prompt_product_type') in (None, '', 'other'):
                context.user_data['prompt_product_type'] = 'other'
            if detected_subtype == 'hijab':
                context.user_data['prompt_product_type'] = 'hijab'
            # Legacy direct-name entry: retain a subtype only if it exactly matches
            # one of the current menu IDs; never pass a guessed alias to the library.
            context.user_data['prompt_product_subcategory'] = (
                detected_subtype if detected_subtype in PRODUCT_SUBTYPE_LABELS else ''
            )
        context.user_data['prompt_custom_category_name'] = ''
        context.user_data['prompt_custom_subcategory_name'] = ''
        context.user_data['prompt_bag_subtype'] = bag_subtype
        context.user_data['prompt_concept'] = ''
        category_label = PRODUCT_TYPES.get(context.user_data.get('prompt_product_type', 'other'), 'Produk umum')
        active_subcategory = context.user_data.get('prompt_product_subcategory', '')
        if active_subcategory in PRODUCT_SUBTYPE_LABELS:
            category_label += ' · ' + PRODUCT_SUBTYPE_LABELS[active_subcategory]
        elif detected_subtype:
            category_label += ' · ' + detected_subtype.replace('_', ' ')
        context.user_data['stage'] = 'prompt_model_presence'
        await update.message.reply_text(
            '✅ Nama produk disimpan: ' + value[:240] + chr(10)
            + '🔎 Kategori: ' + category_label
            + chr(10) * 2 + '👤 Pilih model AI sebelum gaya video:',
            reply_markup=prompt_model_presence_menu(context.user_data)
        )
        return
    shortcuts = {
        '🎬 Jana Video Affiliate': 'make',
        '🎬 Jana Video Transisi': 'make',
        '🎞️ Gerakkan Foto (Transisi)': 'make',
        '✍️ Jana Prompt': 'prompt',
        '🔄 Tukar Format Video': 'convert',
        '✍️ Sediakan Prompt Video': 'prompt',
        '✍️ Hasilkan Prompt': 'prompt',
        '✍️ Prompt': 'prompt',
        '💎 Langganan': 'subscription',
        '👤 Akaun Saya': 'account',
        '🗑 Mula Semula': 'home',
    }
    if value in shortcuts:
        action = shortcuts[value]
        if action == 'make':
            if not await require_paid_feature(update.message, update.effective_user.id):
                return
            reset(context)
            context.user_data['stage'] = 'video_input'
            await update.message.reply_text('🎬 Pilih cara masukkan produk:', reply_markup=video_input_menu())
        elif action == 'convert':
            if not await require_paid_feature(update.message, update.effective_user.id):
                return
            reset(context)
            context.user_data['stage'] = 'convert'
            await update.message.reply_text('🔄 TUKAR FORMAT VIDEO\n\nTekan 📎 → File / Fail → pilih video MP4 asal. Bot akan memprosesnya secara automatik.', reply_markup=main_menu())
        elif action == 'prompt':
            access = await prompt_access_status(update.effective_user.id)
            if not access["available"]:
                await update.message.reply_text("⚠️ Sistem trial belum dapat disemak. Sila cuba lagi kemudian.")
                return
            if not access["allowed"]:
                await update.message.reply_text(
                    "🎁 Anda telah menggunakan 3/3 trial Jana Prompt. Langgan Klippo untuk meneruskan.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💎 Lihat Langganan", callback_data="subscription")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="home")],
                    ])
                )
                return
            reset(context)
            context.user_data['prompt_style'] = 'auto'
            context.user_data['prompt_concept'] = ''
            context.user_data['prompt_product_type'] = 'other'
            context.user_data['prompt_mode'] = 'normal'
            context.user_data['prompt_reference_photos'] = []
            context.user_data['stage'] = 'prompt_product_name'
            await update.message.reply_text(
                '✍️ KLIPPO | JANA PROMPT VIDEO\n\nMasukkan nama produk sahaja. Klippo akan mengesan kategori secara automatik. Selepas itu, pilih durasi dan satu gaya video; kamera, aksi, latar, model, audio, hook dan CTA akan ditetapkan secara automatik.\n\nGambar produk tidak perlu dimuat naik ke bot. Gambar asal boleh digunakan terus pada platform video AI pilihan anda selepas prompt siap.'
            )
        elif action == 'subscription':
            await update.message.reply_text('💎 LANGGANAN KLIPPO\n\nPelan Penyokong Awal: RM2 / 30 hari. Klippo menyediakan prompt dan alat pemprosesan video; penjanaan video AI penuh dilakukan pada platform luaran. Pengaktifan manual selepas resit disemak.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')]]))
        elif action == 'account':
            await account_info(update, context)
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
        await message.reply_text('📝 Tajuk produk Shopee wajib diisi. Sila lengkapkan  selepas Selesai Hantar Gambar.')
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
            custom_background_path = None
            if background == 'custom':
                custom_background_file_id = context.user_data.get('custom_background_file_id')
                if not custom_background_file_id:
                    raise ValueError('Gambar latar sendiri belum diterima. Sila mula semula pilihan latar.')
                custom_background_path = folder / 'custom_background_source'
                custom_background_file = await context.bot.get_file(custom_background_file_id)
                await custom_background_file.download_to_drive(custom_background_path)
            product_layers = []
            if background != 'original':
                for i, path in enumerate(paths):
                    prepared = folder / f'product_bg_{i}.png'
                    foreground_path = folder / f'product_cutout_{i}.png'
                    try:
                        await asyncio.to_thread(replace_background, path, prepared, background, foreground_path, custom_background_path)
                    except ValueError as exc:
                        logging.warning('Background removal declined: %s', exc)
                        alternative = folder / f'shopee_alternative_{i}.jpg'
                        link = context.user_data.get('shopee_url', '')
                        description = context.user_data.get('product_description', '')
                        found = bool(link and await asyncio.to_thread(_shopee_public_photo, link, alternative, description))
                        if found:
                            try:
                                await asyncio.to_thread(replace_background, alternative, prepared, background, foreground_path, custom_background_path)
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
    app.add_handler(CommandHandler('cariuser', admin_user_search))
    app.add_handler(CommandHandler('reset', start))
    app.add_handler(CommandHandler('periksa', status))
    app.add_handler(CommandHandler('jana', generate, block=False))
    app.add_handler(CommandHandler('falbeta', falbeta_start))
    for style in STYLES:
        app.add_handler(CommandHandler(style, choose_style))
    app.add_handler(CallbackQueryHandler(buttons, pattern=r'.+'))
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