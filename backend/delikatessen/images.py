"""Rezeptfotos: auf 1600 px verkleinert, als WebP ohne Metadaten gespeichert (F-01)."""

from __future__ import annotations

import io
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_EDGE = 1600
MAX_UPLOAD = 15_000_000


class ImageError(Exception):
    pass


def save_image(data: bytes, image_dir: Path) -> str:
    if len(data) > MAX_UPLOAD:
        raise ImageError("Das Bild ist zu groß")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((MAX_EDGE, MAX_EDGE))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            image_dir.mkdir(parents=True, exist_ok=True)
            name = f"{secrets.token_hex(12)}.webp"
            # neu kodiert, ohne exif-Parameter: EXIF und andere Metadaten fallen weg
            img.save(image_dir / name, "WEBP", quality=82, method=4)
            return name
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ImageError("Die Datei ist kein lesbares Bild") from e


KI_MAX_EDGE = 1568


def prepare_for_ki(data: bytes) -> bytes:
    """Foto für den KI-Import: gedreht, verkleinert, als JPEG neu kodiert und damit ohne EXIF (N-11)."""
    if len(data) > MAX_UPLOAD:
        raise ImageError("Das Bild ist zu groß")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((KI_MAX_EDGE, KI_MAX_EDGE))
            img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, "JPEG", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ImageError("Die Datei ist kein lesbares Bild") from e


def delete_image(name: str | None, image_dir: Path) -> None:
    if name:
        (image_dir / name).unlink(missing_ok=True)


def valid_name(name: str) -> bool:
    return len(name) == 29 and name.endswith(".webp") and all(c in "0123456789abcdef" for c in name[:24])
