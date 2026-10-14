"""Local product extraction and background compositing.

Optional rembg support if installed; conservative Pillow fallback only for
plain, near-uniform backgrounds. Never silently substitute the original image.
"""
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
    """Simple local interior illustrations, no external assets or added text."""
    w, h = size
    palettes = {
        'living': ((228, 217, 203), (170, 139, 112), (244, 237, 225)),
        'kitchen': ((231, 232, 222), (171, 174, 159), (248, 246, 235)),
        'bedroom': ((222, 215, 220), (164, 146, 158), (242, 234, 232)),
        'garden': ((184, 205, 173), (84, 126, 78), (226, 219, 187)),
    }
    wall, accent, floor = palettes[choice]
    canvas = Image.new('RGBA', size, wall + (255,))
    draw = ImageDraw.Draw(canvas)
    horizon = int(h * .69)
    draw.rectangle((0, horizon, w, h), fill=floor + (255,))
    if choice == 'living':
        draw.rounded_rectangle((int(w*.08), int(h*.20), int(w*.36), int(h*.50)), radius=max(3,w//80), fill=accent+(255,))
        draw.rectangle((int(w*.11),int(h*.23),int(w*.33),int(h*.47)),fill=(241,232,214,255))
        draw.rounded_rectangle((int(w*.64),int(h*.44),int(w*.96),int(h*.70)),radius=max(4,w//35),fill=(190,171,150,255))
    elif choice == 'kitchen':
        draw.rectangle((0,int(h*.31),w,int(h*.36)),fill=(250,249,242,255))
        draw.rectangle((0,int(h*.38),int(w*.28),int(h*.66)),fill=accent+(255,))
        draw.rectangle((int(w*.72),int(h*.38),w,int(h*.66)),fill=accent+(255,))
        draw.rectangle((0,int(h*.66),w,int(h*.70)),fill=(247,245,238,255))
    elif choice == 'bedroom':
        draw.rounded_rectangle((int(w*.62),int(h*.43),w,int(h*.69)),radius=max(4,w//40),fill=accent+(255,))
        draw.rounded_rectangle((int(w*.57),int(h*.56),w,int(h*.70)),radius=max(4,w//40),fill=(244,235,229,255))
        draw.rectangle((int(w*.12),int(h*.22),int(w*.36),int(h*.46)),fill=(245,240,234,255))
    else:
        draw.ellipse((int(-w*.1),int(h*.30),int(w*.42),int(h*.72)),fill=(99,142,87,255))
        draw.ellipse((int(w*.68),int(h*.23),int(w*1.12),int(h*.69)),fill=(107,151,94,255))
        draw.rectangle((0,int(h*.67),w,h),fill=(209,199,166,255))
    return canvas


def replace_background(source: Path, destination: Path, choice: str) -> Path:
    if choice not in BACKGROUNDS and choice not in ('living', 'kitchen', 'bedroom', 'garden'):
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
    background.alpha_composite(foreground)
    background.convert('RGB').save(destination, 'PNG')
    return destination
