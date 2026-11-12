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


ROTATIONS = (0, 90, 180, 270)


def prepare_for_ki(data: bytes, rotation: int = 0) -> bytes:
    """Foto für den KI-Import: gedreht, verkleinert, als JPEG neu kodiert und damit ohne EXIF (N-11).

    rotation: zusätzliche Drehung im Uhrzeigersinn, die in der App gewählt wurde. Fotos von oben auf ein
    flach liegendes Buch speichert das Handy oft mit falscher Lage.
    """
    if len(data) > MAX_UPLOAD:
        raise ImageError("Das Bild ist zu groß")
    if rotation not in ROTATIONS:
        raise ImageError("Ungültige Drehung")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            if rotation:
                img = img.rotate(-rotation, expand=True)
            img.thumbnail((KI_MAX_EDGE, KI_MAX_EDGE))
            img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, "JPEG", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ImageError("Die Datei ist kein lesbares Bild") from e


# Kleiner als das ist kein brauchbares Rezeptbild, eher eine Fehlangabe der KI
MIN_CROP_EDGE = 200


def crop_dish(data: bytes, box: tuple[int, int, int, int], rotation: int, image_dir: Path) -> str | None:
    """Schneidet das Gerichtsbild aus einem Foto (Rand in Promille) und speichert es wie ein Rezeptfoto.

    None, wenn der Rand unbrauchbar ist. Etwas Luft am Rand gleicht ungenaue Angaben der KI aus.
    """
    left, top, right, bottom = (max(0, min(1000, v)) for v in box)
    if right - left < 50 or bottom - top < 50 or rotation not in ROTATIONS:
        return None
    try:
        with Image.open(io.BytesIO(data)) as img:
            w, h = img.size
            pad = 0.01
            area = (
                round(max(0.0, left / 1000 - pad) * w),
                round(max(0.0, top / 1000 - pad) * h),
                round(min(1.0, right / 1000 + pad) * w),
                round(min(1.0, bottom / 1000 + pad) * h),
            )
            if min(area[2] - area[0], area[3] - area[1]) < MIN_CROP_EDGE:
                return None
            part = img.crop(area)
            if rotation:
                part = part.rotate(-rotation, expand=True)
            out = io.BytesIO()
            part.convert("RGB").save(out, "PNG")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return None
    return save_image(out.getvalue(), image_dir)


def delete_image(name: str | None, image_dir: Path) -> None:
    if name:
        (image_dir / name).unlink(missing_ok=True)


def valid_name(name: str) -> bool:
    return len(name) == 29 and name.endswith(".webp") and all(c in "0123456789abcdef" for c in name[:24])
