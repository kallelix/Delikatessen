"""Sicheres Laden fremder Seiten beim Link-Import (Abschnitt 11, Risiko interne Adressen)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (compatible; Delikatessen-Rezeptimport/1.0)"


class FetchError(Exception):
    """Fehler mit einer Meldung, die in der Vorschau angezeigt werden darf."""


def _check_url(url: str, allow_private: bool) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("Nur http- und https-Links sind erlaubt")
    if not parts.hostname:
        raise FetchError("Der Link enthält keinen Servernamen")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as e:
        raise FetchError("Der Server ist nicht bekannt") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise FetchError("Interne oder lokale Adressen sind gesperrt")


def fetch(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    allow_private: bool = False,
    accept: str = "text/html,application/xhtml+xml",
) -> tuple[str, bytes, str]:
    """Lädt eine Adresse und prüft jede Weiterleitung. Gibt (finale URL, Inhalt, Content-Type) zurück."""
    headers = {"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "de,en;q=0.5"}
    with httpx.Client(follow_redirects=False, timeout=timeout, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _check_url(url, allow_private)
            try:
                with client.stream("GET", url) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise FetchError("Weiterleitung ohne Ziel")
                        url = urljoin(url, location)
                        continue
                    if resp.status_code >= 400:
                        raise FetchError(f"Die Seite antwortet mit Fehler {resp.status_code}")
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise FetchError("Die Seite ist zu groß")
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise FetchError("Die Seite ist zu groß")
                    return url, bytes(body), resp.headers.get("content-type", "")
            except httpx.TimeoutException as e:
                raise FetchError("Die Seite hat zu lange gebraucht") from e
            except httpx.HTTPError as e:
                raise FetchError("Die Seite ließ sich nicht laden") from e
    raise FetchError("Zu viele Weiterleitungen")
