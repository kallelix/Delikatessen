"""Web Push mit VAPID (F-24, Abschnitt 2). Nur ausgehende Verbindungen zum Push-Dienst des Browsers.

Nachrichten enthalten keine Rezeptdetails, nur einen Hinweis und den Pfad in der App. Abgelaufene
Abonnements (404, 410) werden gelöscht.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import PushSubscription

log = logging.getLogger(__name__)

TTL_S = 24 * 60 * 60

# (Abonnement, Text der Nachricht) -> nichts, wirft bei Fehlern WebPushException
Sender = Callable[[dict, str], None]


def key_path(settings: Settings) -> Path:
    return settings.data_dir / "vapid_private.pem"


def _vapid(settings: Settings):
    from py_vapid import Vapid

    path = key_path(settings)
    if not path.exists():
        # beim ersten Bedarf erzeugen, nur für den Dienst lesbar. Liegt im Datenverzeichnis und ist damit gesichert.
        path.parent.mkdir(parents=True, exist_ok=True)
        v = Vapid()
        v.generate_keys()
        v.save_key(str(path))
        os.chmod(path, 0o600)
    return Vapid.from_file(str(path))


def public_key(settings: Settings) -> str:
    from py_vapid import b64urlencode

    raw = _vapid(settings).public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64urlencode(raw)


def live_sender(settings: Settings) -> Sender:
    def send(subscription: dict, data: str) -> None:
        from pywebpush import webpush

        webpush(
            subscription_info=subscription,
            data=data,
            vapid_private_key=str(key_path(settings)),
            vapid_claims={"sub": settings.push_contact},
            ttl=TTL_S,
            timeout=10,
        )

    _vapid(settings)  # Schlüssel sicherstellen
    return send


def subscription_info(s: PushSubscription) -> dict:
    return {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}}


def send_all(
    session: Session,
    sender: Sender,
    title: str,
    body: str,
    url: str = "/",
    only: list[PushSubscription] | None = None,
) -> dict:
    """Schickt eine Nachricht an alle (oder die genannten) Geräte. Gibt gesendet, entfernt, fehler zurück."""
    from pywebpush import WebPushException

    data = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
    subs = only if only is not None else list(session.scalars(select(PushSubscription)))
    sent = removed = failed = 0
    for s in subs:
        try:
            sender(subscription_info(s), data)
            sent += 1
        except WebPushException as e:
            if e.status_code in (404, 410):
                session.delete(s)
                removed += 1
            else:
                log.warning("Push an ein Gerät fehlgeschlagen: Status %s", e.status_code)
                failed += 1
        except Exception as e:  # Netz, Zeitüberschreitung: das nächste Gerät trotzdem versuchen
            log.warning("Push an ein Gerät fehlgeschlagen: %s", type(e).__name__)
            failed += 1
    session.commit()
    return {"gesendet": sent, "entfernt": removed, "fehler": failed}


def status(session: Session) -> dict:
    n = len(session.scalars(select(PushSubscription.id)).all())
    if n == 0:
        return {"aktiv": False, "hinweis": "noch kein Gerät angemeldet"}
    return {"aktiv": True, "hinweis": f"{n} Gerät{'e' if n != 1 else ''}"}
