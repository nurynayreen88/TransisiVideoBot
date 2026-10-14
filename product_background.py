"""Local product extraction and background compositing.

Optional rembg support if installed; conservative Pillow fallback only for
plain, near-uniform backgrounds. Never silently substitute the original image.
"""
from collections import deque
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter

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
        pix[x, y] = (0, 0, 0)
        for xx, yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= xx < w and 0 <= yy < h and not visited[yy*w+xx]:
                queue.append((xx, yy))
    mask = Image.new('L', (w, h))
    mask.putdata([0 if pix[x,y] == (0,0,0) and visited[y*w+x] else 255
                  for y in range(h) for x in range(w)])
    bbox = mask.getbbox()
    if not bbox or bbox[0] == 0 or bbox[1] == 0 or bbox[2] == w or bbox[3] == h:
        raise ValueError('Product touches the image boundary or segmentation uncertain')
    area = sum(v > 127 for v in mask.getdata()) / (w*h)
    if not .025 <= area <= .85:
        raise ValueError('Uncertain product area')
    return mask.resize(image.size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(0.65))


def replace_background(source: Path, destination: Path, choice: str) -> Path:
    if choice not in BACKGROUNDS:
        raise ValueError('Unknown background')
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGB')
    # Use an installed segmentation model where available, without requiring
    # an external paid API or silently downloading one during every request.
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
    background = Image.new('RGBA', foreground.size, BACKGROUNDS[choice] + (255,))
    background.alpha_composite(foreground)
    background.convert('RGB').save(destination, 'PNG')
    return destination
