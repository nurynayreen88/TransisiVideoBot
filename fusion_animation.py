"""Use the user's original fusion GIF clips. Keep a safe fallback for deployment."""
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw

def fusion_gif(success=False):
    filename = "fusion_success.gif" if success else "fusion_loading.gif"
    path = Path(__file__).resolve().parent / "fusion_assets" / filename
    if path.is_file():
        result = BytesIO(path.read_bytes())
        result.name = filename
        return result
    import logging
    logging.warning("Fusion asset missing: %s; using placeholder", path)
    image = Image.new("RGB", (220, 165), (22, 28, 64))
    draw = ImageDraw.Draw(image)
    draw.text((24, 70), "Gabungan berjaya!" if success else "Menggabungkan video...", fill="white")
    result = BytesIO()
    image.save(result, format="GIF")
    result.seek(0)
    result.name = "fallback.gif"
    return result
