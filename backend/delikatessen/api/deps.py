"""Gemeinsame Abhängigkeiten der Endpunkte: Datenbank, heutiges Datum, aktuelles Profil (N-09)."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterator
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Person

PERSON_HEADER = "X-Delikatessen-Person"


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.db.sessionmaker() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_today(request: Request) -> date:
    override = getattr(request.app.state, "today_override", None)
    if override is not None:
        return override
    return datetime.now(ZoneInfo(request.app.state.settings.timezone)).date()


def client_ip(request: Request, settings: Settings) -> str | None:
    """Herkunftsadresse. X-Forwarded-For gilt nur, wenn die Anfrage vom nginx-LXC kommt."""
    host = request.client.host if request.client else None
    if host is None:
        return None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and any(ip in net for net in settings.trusted_proxy_networks):
        return forwarded.split(",")[-1].strip()
    return host


def current_person(
    request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> Person | None:
    raw = request.headers.get(PERSON_HEADER)
    if raw and raw.isdigit():
        person = db.get(Person, int(raw))
        if person is not None:
            return person
    ip = client_ip(request, settings)
    if ip:
        return db.scalar(select(Person).where(Person.netbird_ip == ip))
    return None


def require_adult(person: Person | None = Depends(current_person), db: Session = Depends(get_db)) -> None:
    """Bedienschutz: Einstellungen und Familie nur für Erwachsene. Ohne Familie ist alles erlaubt."""
    if person is not None and person.kind == "erwachsen":
        return
    if person is None and db.scalar(select(Person.id).limit(1)) is None:
        return
    raise HTTPException(403, "Nur für Erwachsene")
