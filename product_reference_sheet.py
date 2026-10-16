"""Create a loss-minimizing product reference sheet for ChatGPT analysis.

This module performs layout only. It never regenerates, edits, or infers product features.
"""
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps, ImageDraw


MAX_REFERENCE_IMAGES = 8
CELL_SIZE = (1260, 900)
MARGIN = 48
GAP = 36

CHATGPT_ANALYSIS_PROMPT = """Analisis helaian gambar produk yang saya muat naik. Helaian ini mengandungi beberapa foto bagi produk yang sama. Periksa setiap panel dan gunakan semuanya sebagai rujukan visual.

TUGAS A — GAMBAR PRODUK
Hasilkan satu gambar produk promosi yang realistik, kemas dan berkualiti tinggi dalam format menegak 9:16, sesuai sebagai imej rujukan untuk video produk. Kekalkan identiti produk berdasarkan foto asal: bentuk, perkadaran, warna, corak, komponen dan logo/jenama yang memang kelihatan. Jangan mereka-reka ciri, aksesori, bahan atau fungsi. Jangan tambah teks, slogan, label, watermark atau logo baharu pada gambar. Jika sudut atau butiran tidak kelihatan, jangan reka butiran tersebut. Jangan ubah produk menjadi kartun.

TUGAS B — MAKLUMAT PRODUK UNTUK KLIPPO
Selepas arahan gambar, keluarkan satu blok teks ringkas menggunakan format tepat di bawah. Isikan berdasarkan perkara yang benar-benar kelihatan atau maklumat yang diberikan. Jika bahan atau ciri tidak dapat dipastikan, tulis “Tidak dapat dipastikan daripada gambar”. Jangan masukkan dakwaan promosi yang tidak disahkan.

MAKLUMAT PRODUK UNTUK KLIPPO
NAMA PRODUK:
KATEGORI:
WARNA:
REKA BENTUK:
BAHAN:
BUTIRAN VISUAL:
CIRI YANG WAJIB DIKEKALKAN:
GAYA VIDEO: REALISTIK + DOODLE
ARAHAN VISUAL: Kekalkan produk realistik sebagai fokus utama. Tambahkan doodle bergerak yang kemas di sekeliling produk, tanpa menutup atau mengubah produk.

Pastikan blok MAKLUMAT PRODUK UNTUK KLIPPO mudah disalin dan tidak melebihi 1,800 aksara. Jangan masukkan arahan panjang lain ke dalam blok maklumat itu."""


def build_reference_sheet(image_paths: Iterable[Path], output_path: Path) -> Path:
    """Arrange up to eight source images into one high-resolution, uncropped sheet."""
    paths = list(image_paths)
    if not paths:
        raise ValueError("Sekurang-kurangnya satu gambar diperlukan.")
    if len(paths) > MAX_REFERENCE_IMAGES:
        raise ValueError(f"Maksimum {MAX_REFERENCE_IMAGES} gambar bagi satu helaian.")

    columns = 2 if len(paths) > 1 else 1
    rows = (len(paths) + columns - 1) // columns
    cell_w, cell_h = CELL_SIZE
    width = MARGIN * 2 + columns * cell_w + (columns - 1) * GAP
    height = MARGIN * 2 + rows * cell_h + (rows - 1) * GAP
    sheet = Image.new("RGB", (width, height), (248, 247, 244))
    draw = ImageDraw.Draw(sheet)

    for index, path in enumerate(paths):
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((cell_w - 32, cell_h - 32), Image.Resampling.LANCZOS)

        col = index % columns
        row = index // columns
        x = MARGIN + col * (cell_w + GAP)
        y = MARGIN + row * (cell_h + GAP)
        draw.rounded_rectangle(
            (x, y, x + cell_w, y + cell_h),
            radius=18,
            fill=(255, 255, 255),
            outline=(224, 222, 217),
            width=3,
        )
        px = x + (cell_w - image.width) // 2
        py = y + (cell_h - image.height) // 2
        sheet.paste(image, (px, py))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="JPEG", quality=92, optimize=True, progressive=True, subsampling=0)
    return output_path
