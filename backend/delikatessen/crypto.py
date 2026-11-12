"""Verschlüsselt Zugangsdaten mit dem Schlüssel aus der Konfiguration (Abschnitt 11)."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretError(Exception):
    pass


def _fernet(secret_key: str | None) -> Fernet:
    if not secret_key:
        raise SecretError("DELIKATESSEN_SECRET_KEY fehlt in der Konfiguration (/etc/delikatessen/env)")
    # beliebig langer Schlüssel aus der env-Datei, Fernet braucht genau 32 Byte
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest()))


def encrypt(secret_key: str | None, text: str) -> str:
    return _fernet(secret_key).encrypt(text.encode()).decode()


def decrypt(secret_key: str | None, token: str) -> str:
    try:
        return _fernet(secret_key).decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise SecretError("Gespeicherte Zugangsdaten passen nicht zum Schlüssel, bitte neu eingeben") from e
