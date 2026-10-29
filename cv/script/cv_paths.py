"""Lokasi aset CV, independen dari working directory terminal."""

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATASETS_DIR = SCRIPT_DIR / "datasets"
MODELS_DIR = SCRIPT_DIR / "models"
MEDIA_DIR = SCRIPT_DIR / "media"
OUTPUTS_DIR = SCRIPT_DIR / "outputs"


def output_path(*parts):
    """Siapkan parent output dan kembalikan string untuk OpenCV/open()."""
    path = OUTPUTS_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)
