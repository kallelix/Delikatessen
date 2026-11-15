"""Update-Hinweis und Update auf Knopfdruck (docs/betrieb.md, Abschnitt 4).

Die App selbst spricht dafür kein Netz an und braucht keine root-Rechte:

- Ein systemd-Timer auf dem Host schreibt täglich das neueste Release nach `<update_dir>/neueste.json`.
  „Jetzt prüfen“ legt `<data_dir>/update-pruefen` an, dann startet delikatessen-update-check.path dieselbe
  Prüfung sofort.
- Der Knopf legt nur die Datei `<data_dir>/update-anfrage` an. Eine systemd-Path-Unit startet dann als root
  `deploy/selbst-update.sh`, das immer das neueste Release installiert. Die App kann weder Version noch
  Parameter wählen. Den Verlauf schreibt das Skript nach `<update_dir>/update.json`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .config import Settings

REQUEST_FILE = "update-anfrage"
CHECK_FILE = "update-pruefen"
# Bleibt die Anforderung zum Prüfen länger liegen, fehlt die Path-Unit oder sie hängt: wieder freigeben
CHECK_STALE_AFTER = timedelta(minutes=2)
# Läuft ein Update länger, gilt es als hängengeblieben und der Knopf ist wieder frei
STALE_AFTER = timedelta(minutes=30)


def parse_version(text: str | None) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def request_path(settings: Settings) -> Path:
    return settings.data_dir / REQUEST_FILE


def check_path(settings: Settings) -> Path:
    return settings.data_dir / CHECK_FILE


def _checking(settings: Settings, now: datetime) -> bool:
    try:
        since = datetime.fromtimestamp(check_path(settings).stat().st_mtime).astimezone()
    except OSError:
        return False
    return now - since < CHECK_STALE_AFTER


def _running(last: dict | None, now: datetime) -> bool:
    if not last or last.get("status") != "laeuft":
        return False
    try:
        since = datetime.fromisoformat(str(last.get("zeit")))
    except ValueError:
        return False
    return now - since.astimezone() < STALE_AFTER


def status(settings: Settings, now: datetime | None = None) -> dict | None:
    """Stand für "Mehr" › "Status der Dienste". None, wenn der Host keine Update-Prüfung eingerichtet hat."""
    if settings.update_dir is None:
        return None
    now = now or datetime.now().astimezone()
    latest = _read(settings.update_dir / "neueste.json") or {}
    last = _read(settings.update_dir / "update.json")
    current, newest = parse_version(__version__), parse_version(latest.get("neueste"))
    available = bool(current and newest and newest > current)
    requested = request_path(settings).exists()
    return {
        "version": __version__,
        "neueste": latest.get("neueste"),
        "url": latest.get("url"),
        "geprueft": latest.get("geprueft"),
        "verfuegbar": available,
        "knopf": settings.update_button,
        "laeuft": requested or _running(last, now),
        "prueft": _checking(settings, now),
        "letztes": last,
    }


class UpdateRefused(Exception):
    pass


def request_update(settings: Settings) -> None:
    """Legt die Anforderung für die Path-Unit an. Der Inhalt wird nie gelesen, nur ihr Dasein zählt."""
    s = status(settings)
    if s is None or not settings.update_button:
        raise UpdateRefused("Update per Knopf ist auf diesem Server nicht eingerichtet")
    if s["laeuft"]:
        raise UpdateRefused("Ein Update läuft schon")
    if not s["verfuegbar"]:
        raise UpdateRefused("Es gibt keine neuere Version")
    request_path(settings).touch()


def request_check(settings: Settings) -> None:
    """Legt die Anforderung für delikatessen-update-check.path an. Zweimal drücken schadet nicht."""
    if status(settings) is None:
        raise UpdateRefused("Die Update-Prüfung ist auf diesem Server nicht eingerichtet")
    check_path(settings).touch()
