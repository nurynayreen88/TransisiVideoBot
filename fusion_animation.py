"""Klippo fusion animation assets, provided by the project owner."""
from io import BytesIO
from pathlib import Path

ASSET_DIR = Path(__file__).resolve().parent / "fusion_assets"

def fusion_gif(success=False):
    filename = "fusion_success.gif" if success else "fusion_loading.gif"
    path = ASSET_DIR / filename
    data = BytesIO(path.read_bytes())
    data.name = filename
    return data
