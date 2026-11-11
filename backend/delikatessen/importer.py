"""Link-Import als Hintergrundauftrag, endet in einer Vorschau (D-LINK, Abschnitt 7)."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from html import unescape

from recipe_scrapers import scrape_html
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .catalog import Matcher
from .config import Settings
from .models import ImportJob
from .netguard import FetchError, fetch
from .units import parse_ingredient_line

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


def preview_ingredients(session: Session, lines: list[str]) -> list[dict]:
    matcher = Matcher(session)
    out = []
    for line in lines:
        if not line or not line.strip():
            continue
        p = parse_ingredient_line(line)
        ingredient_id = matcher.match(p.name)
        out.append(
            {
                "line": p.line,
                "amount": p.amount,
                "unit": p.unit,
                "name": p.name,
                "note": p.note,
                "ingredient_id": ingredient_id,
                "ingredient_name": matcher.names.get(ingredient_id) if ingredient_id else None,
            }
        )
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


def run_link_job(sm: sessionmaker, settings: Settings, job_id: int) -> None:
    with sm() as session:
        job = session.get(ImportJob, job_id)
        if job is None or job.status not in ("wartet", "laeuft"):
            return
        job.status = "laeuft"
        session.commit()
        try:
            final_url, body, ctype = fetch(
                job.source,
                timeout=settings.fetch_timeout_s,
                max_bytes=settings.fetch_max_bytes,
                allow_private=settings.allow_private_fetch,
            )
            status, result = extract(session, _decode(body, ctype), final_url)
            job.status, job.result = status, result
        except FetchError as e:
            job.status, job.error = "fehler", str(e)
        except Exception:
            log.exception("Import %s fehlgeschlagen", job_id)
            job.status, job.error = "fehler", "Unerwarteter Fehler beim Lesen der Seite"
        session.commit()


class ImportRunner:
    def __init__(self, sm: sessionmaker, settings: Settings):
        self.sm = sm
        self.settings = settings
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="import")

    def submit(self, job_id: int) -> None:
        self.pool.submit(run_link_job, self.sm, self.settings, job_id)

    def resume_pending(self) -> None:
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
