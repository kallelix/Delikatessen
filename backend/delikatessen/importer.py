"""Link-Import als Hintergrundauftrag, endet in einer Vorschau (D-LINK, Abschnitt 7)."""

from __future__ import annotations

import logging
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup
from recipe_scrapers import scrape_html
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .catalog import Matcher
from .config import Settings
from .images import crop_dish
from .ki import KiClient, KiError, KiRecipe
from .models import ImportJob, Tag
from .netguard import FetchError, fetch
from .units import ParsedLine, format_quantity, normalize_unit, parse_ingredient_line

log = logging.getLogger(__name__)


def _decode(body: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    if not m:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
    charset = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)) if m else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _safe(fn, default=None):
    try:
        value = fn()
    except Exception:  # recipe-scrapers wirft je nach Seite sehr unterschiedliche Fehler
        return default
    return value if value not in ("", None, []) else default


def _servings(yields: str | None) -> int | None:
    if not yields:
        return None
    m = re.search(r"\d+", str(yields))
    return int(m.group()) if m and 0 < int(m.group()) <= 100 else None


def _page_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return " ".join(unescape(m.group(1)).split())[:200] if m else None


# Trennt Sammelzeilen wie "Salz und Pfeffer" oder "Salz, Pfeffer, Muskat". "oder" und "/" bleiben stehen,
# weil sie Alternativen meinen.
_SPLIT_RE = re.compile(r"\s*(?:,|;|&|\+|\bund\b|\bsowie\b)\s*", re.IGNORECASE)
# Bei diesen Einheiten gilt die Menge für jede Zutat: "1 Prise Salz und Pfeffer"
_PER_ITEM_UNITS = {"Prise", "Msp."}


def _match_part(matcher: Matcher, text: str) -> tuple[int, str, str | None] | None:
    """Ordnet einen Teil zu, notfalls ohne vorangestellte Beschreibung ("frisch gemahlener Pfeffer")."""
    words = text.split()
    for i in range(len(words)):
        candidate = " ".join(words[i:])
        ingredient_id = matcher.match(candidate)
        if ingredient_id:
            return ingredient_id, candidate, " ".join(words[:i]) or None
    return None


def _split_combined(p: ParsedLine, matcher: Matcher) -> list[tuple[int, str, str | None, float | None, str | None]]:
    """Zerlegt eine Sammelzeile, aber nur, wenn jeder Teil im Katalog steht ("Knoblauch, gehackt" bleibt ganz)."""
    if not p.body or matcher.match(p.body):
        return []
    parts = [s.strip(" -–:;.") for s in _SPLIT_RE.split(p.body)]
    parts = [s for s in parts if s]
    if len(parts) < 2:
        return []
    matched = [_match_part(matcher, s) for s in parts]
    if not all(matched):
        return []
    if p.amount is None or p.unit in _PER_ITEM_UNITS:
        amount, unit, total = p.amount, p.unit, None
    else:
        # "200 g Erbsen und Möhren": wie viel wovon, steht nicht da
        amount, unit, total = None, None, f"zusammen {format_quantity(p.amount, p.unit)}"
    out = []
    for ingredient_id, name, description in matched:
        notes = [*p.base_notes, *(n for n in (description, total) if n)]
        out.append((ingredient_id, name, ", ".join(notes) or None, amount, unit))
    return out


def preview_ingredients(session: Session, lines: list[str]) -> list[dict]:
    matcher = Matcher(session)
    out = []

    def add(line: str, amount, unit, name: str, note, ingredient_id: int | None) -> None:
        out.append(
            {
                "line": line,
                "amount": amount,
                "unit": unit,
                "name": name,
                "note": note,
                "ingredient_id": ingredient_id,
                "ingredient_name": matcher.names.get(ingredient_id) if ingredient_id else None,
            }
        )

    for line in lines:
        if not line or not line.strip():
            continue
        p = parse_ingredient_line(line)
        split = _split_combined(p, matcher)
        if split:
            for ingredient_id, name, note, amount, unit in split:
                add(p.line, amount, unit, name, note, ingredient_id)
        else:
            add(p.line, p.amount, p.unit, p.name, p.note, matcher.match(p.name))
    return out


def extract(session: Session, html: str, url: str) -> tuple[str, dict]:
    """Liest Schema-Daten. Gibt (status, ergebnis) zurück: fertig oder ohne_schema."""
    try:
        scraper = scrape_html(html, org_url=url, supported_only=False)
    except Exception:
        scraper = None
    title = _safe(lambda: scraper.title()) if scraper else None
    ingredients = _safe(lambda: scraper.ingredients(), []) if scraper else []
    if not title or not ingredients:
        return "ohne_schema", {"title": title or _page_title(html), "source_url": url}
    total = _safe(lambda: scraper.total_time())
    steps = _safe(lambda: scraper.instructions_list(), [])
    if not steps:
        text = _safe(lambda: scraper.instructions(), "")
        steps = [s.strip() for s in text.split("\n") if s.strip()]
    return "fertig", {
        "title": " ".join(str(title).split())[:200],
        "servings": _servings(_safe(lambda: scraper.yields())) or 4,
        "duration_min": int(total) if isinstance(total, (int, float)) and 0 < total < 24 * 60 else None,
        "size": "haupt",
        "steps": [" ".join(s.split()) for s in steps],
        "ingredients": preview_ingredients(session, ingredients),
        "image_url": _safe(lambda: scraper.image()),
        "source_url": url,
    }


def page_text(html: str) -> str:
    """Sichtbarer Text einer Seite ohne Skripte, Menüs und Fußzeilen, für die KI."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe"]):
        tag.decompose()
    lines = (" ".join(line.split()) for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def ki_preview(session: Session, recipe: KiRecipe, source_url: str | None = None) -> dict:
    """Antwort der KI in dieselbe Vorschau wie beim Link-Import: Zutaten dem Katalog zuordnen, Tags auflösen."""
    matcher = Matcher(session)
    tags = {t.name.lower(): t.id for t in session.scalars(select(Tag))}
    ingredients = []
    for i in recipe.ingredients:
        name = " ".join(i.name.split())[:200]
        if not name:
            continue
        ingredient_id = matcher.match(name)
        ingredients.append(
            {
                "line": i.line,
                "amount": i.amount if i.amount and i.amount > 0 else None,
                "unit": (normalize_unit(i.unit) or "")[:20] or None,
                "name": name,
                "note": i.note or None,
                "ingredient_id": ingredient_id,
                "ingredient_name": matcher.names.get(ingredient_id) if ingredient_id else None,
            }
        )
    return {
        "title": " ".join((recipe.title or "").split())[:200] or None,
        "servings": recipe.servings if recipe.servings and 0 < recipe.servings <= 100 else 4,
        "duration_min": recipe.duration_min if recipe.duration_min and 0 < recipe.duration_min < 24 * 60 else None,
        "size": recipe.size or "haupt",
        "steps": [" ".join(s.split()) for s in recipe.steps if s.strip()],
        "tag_ids": sorted({tags[t.lower()] for t in recipe.tags if t.lower() in tags}),
        "ingredients": ingredients,
        "image_url": None,
        "source_url": source_url,
        "ki": True,
    }


def photo_dir(settings: Settings, job_id: int) -> Path:
    return settings.data_dir / "import" / str(job_id)


def dish_image(settings: Settings, job_id: int) -> Path | None:
    """Ausgeschnittenes Gerichtsbild eines Foto-Imports, bis es übernommen oder verworfen ist."""
    folder = photo_dir(settings, job_id)
    return next(iter(sorted(folder.glob("*.webp"))), None) if folder.is_dir() else None


def _crop_dish(recipe: KiRecipe, images: list[bytes], folder: Path) -> bool:
    d = recipe.dish_photo
    if d is None or not 1 <= d.image <= len(images):
        return False
    return crop_dish(images[d.image - 1], (d.left, d.top, d.right, d.bottom), d.rotation, folder) is not None


def _ki_recipe(session: Session, ki: KiClient, *, text: str | None = None, images: list[bytes] = ()) -> KiRecipe:
    tag_names = list(session.scalars(select(Tag.name).order_by(Tag.name)))
    recipe = ki.extract(text=text, images=images, tag_names=tag_names)
    if not recipe.found or not recipe.ingredients:
        raise KiError("Darin hat die KI kein Rezept gefunden")
    return recipe


def run_job(sm: sessionmaker, settings: Settings, job_id: int, ki_factory=None) -> None:
    """Führt einen Importauftrag aus: Link (erst Schema-Daten, sonst KI), Text oder Fotos (nur KI)."""
    with sm() as session:
        job = session.get(ImportJob, job_id)
        if job is None or job.status not in ("wartet", "laeuft"):
            return
        job.status = "laeuft"
        session.commit()
        ki_factory = ki_factory or KiClient
        try:
            if job.kind == "link":
                final_url, body, ctype = fetch(
                    job.source,
                    timeout=settings.fetch_timeout_s,
                    max_bytes=settings.fetch_max_bytes,
                    allow_private=settings.allow_private_fetch,
                )
                html = _decode(body, ctype)
                status, result = extract(session, html, final_url)
                if status == "ohne_schema" and settings.ki_configured:
                    # ab Stufe 2: Seiten ohne Rezeptdaten liest die KI (Abschnitt 7)
                    try:
                        recipe = _ki_recipe(session, ki_factory(settings), text=page_text(html))
                        status, result = "fertig", ki_preview(session, recipe, final_url)
                    except KiError as e:
                        job.error = str(e)
                job.status, job.result = status, result
            elif job.kind == "text":
                recipe = _ki_recipe(session, ki_factory(settings), text=job.source)
                job.status, job.result = "fertig", ki_preview(session, recipe)
            elif job.kind == "foto":
                folder = photo_dir(settings, job_id)
                images = [p.read_bytes() for p in sorted(folder.glob("*.jpg"))]
                if not images:
                    raise KiError("Die Fotos sind nicht mehr da, bitte erneut aufnehmen")
                recipe = _ki_recipe(session, ki_factory(settings), images=images)
                job.status, job.result = "fertig", ki_preview(session, recipe)
                if _crop_dish(recipe, images, folder):
                    job.result = {**job.result, "image_url": f"/api/v1/imports/{job_id}/bild"}
            else:
                job.status, job.error = "fehler", "Unbekannte Importart"
        except (FetchError, KiError) as e:
            job.status, job.error = "fehler", str(e)
        except Exception:
            log.exception("Import %s fehlgeschlagen", job_id)
            job.status, job.error = "fehler", "Unerwarteter Fehler beim Import"
        if job.kind == "foto":
            # Fotos liegen nur bis zur Auswertung auf dem Server, das Gerichtsbild bis zur Übernahme
            folder = photo_dir(settings, job_id)
            for p in folder.glob("*.jpg"):
                p.unlink(missing_ok=True)
            if dish_image(settings, job_id) is None:
                shutil.rmtree(folder, ignore_errors=True)
        session.commit()


# Nicht übernommene Gerichtsbilder werden nach dieser Zeit beim Start entfernt
STALE_IMPORT_S = 7 * 24 * 3600


def cleanup_import_dirs(sm: sessionmaker, settings: Settings) -> None:
    root = settings.data_dir / "import"
    if not root.is_dir():
        return
    with sm() as session:
        busy = {str(i) for i in session.scalars(select(ImportJob.id).where(ImportJob.status.in_(("wartet", "laeuft"))))}
    for folder in root.iterdir():
        if folder.is_dir() and folder.name not in busy and time.time() - folder.stat().st_mtime > STALE_IMPORT_S:
            shutil.rmtree(folder, ignore_errors=True)


class ImportRunner:
    def __init__(self, sm: sessionmaker, settings: Settings):
        self.sm = sm
        self.settings = settings
        self.ki_factory = KiClient  # Tests ersetzen das durch eine Attrappe
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="import")

    def submit(self, job_id: int) -> None:
        self.pool.submit(run_job, self.sm, self.settings, job_id, self.ki_factory)

    def resume_pending(self) -> None:
        cleanup_import_dirs(self.sm, self.settings)
        with self.sm() as session:
            ids = session.scalars(select(ImportJob.id).where(ImportJob.status.in_(("wartet", "laeuft"))))
            for job_id in ids:
                self.submit(job_id)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)


def download_image(url: str, settings: Settings) -> bytes | None:
    try:
        _, body, ctype = fetch(
            url,
            timeout=settings.fetch_timeout_s,
            max_bytes=15_000_000,
            allow_private=settings.allow_private_fetch,
            accept="image/*",
        )
    except FetchError:
        return None
    return body if ctype.startswith("image/") or not ctype else None
