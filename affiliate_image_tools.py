"""Lightweight affiliate image tools. No external API or video transcoding."""
from io import BytesIO
from PIL import Image, ImageOps, ImageDraw, ImageFont

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000
SIZES = {'square': (1080, 1080), 'portrait': (1080, 1350), 'story': (1080, 1920), 'wide': (1280, 720)}

def _open(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Image must be 5 MB or smaller')
    with Image.open(BytesIO(raw)) as src:
        if src.format not in ('JPEG', 'PNG', 'WEBP'):
            raise ValueError('Only JPG, PNG or WebP supported')
        if src.width * src.height > MAX_PIXELS:
            raise ValueError('Image exceeds 12 megapixels')
        im = ImageOps.exif_transpose(src).convert('RGBA')
        im.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        return im.copy()

def _font(size):
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()

def _text(draw, text, xy, max_width, initial=64, fill='white', stroke=3):
    text = text.strip()[:80]
    if not text:
        raise ValueError('Text is required')
    for size in range(initial, 15, -2):
        font = _font(size)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        if box[2] - box[0] <= max_width:
            break
    draw.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill='#222222')

def _save(im):
    out = BytesIO()
    im.convert('RGB').save(out, 'JPEG', quality=88, optimize=True)
    out.seek(0)
    out.name = 'Klippo_Affiliate.jpg'
    return out

def render(tool, images, value='', ratio='story'):
    if tool not in ('cover', 'sticker', 'resize', 'compare') or ratio not in SIZES:
        raise ValueError('Invalid tool')
    if len(images) != (2 if tool == 'compare' else 1):
        raise ValueError('Wrong number of images')
    source = [_open(raw) for raw in images]
    size = SIZES[ratio]
    if tool == 'resize':
        canvas = Image.new('RGB', size, '#f5f5f5')
        fitted = source[0].copy()
        fitted.thumbnail((size[0]-60, size[1]-60), Image.Resampling.LANCZOS)
        canvas.paste(fitted, ((size[0]-fitted.width)//2, (size[1]-fitted.height)//2), fitted)
        return _save(canvas)
    if tool == 'compare':
        canvas = Image.new('RGB', size, 'white')
        half = size[0] // 2
        for i, im in enumerate(source):
            panel = ImageOps.fit(im.convert('RGB'), (half, size[1]), method=Image.Resampling.LANCZOS)
            canvas.paste(panel, (i*half, 0))
        ImageDraw.Draw(canvas).line((half, 0, half, size[1]), fill='white', width=8)
        return _save(canvas)
    canvas = ImageOps.fit(source[0].convert('RGB'), size, method=Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(canvas)
    if tool == 'cover':
        draw.rectangle((0, size[1]-290, size[0], size[1]), fill='#252525')
        _text(draw, value, (55, size[1]-230), size[0]-110, 66)
    else:
        draw.rounded_rectangle((30, 30, min(size[0]-30, 620), 170), radius=25, fill='#cc2936')
        _text(draw, value, (55, 66), min(size[0]-110, 540), 60)
    return _save(canvas)
