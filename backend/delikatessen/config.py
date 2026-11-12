"""Konfiguration aus Umgebungsvariablen (Präfix DELIKATESSEN_) oder einer env-Datei (N-16)."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DELIKATESSEN_", env_file=None, extra="ignore")

    # Verzeichnis für Datenbank und Bilder
    data_dir: Path = Path("./data")
    # Adressen, deren X-Forwarded-For akzeptiert wird (der nginx-LXC), durch Kommas getrennt
    trusted_proxies: str = "127.0.0.1"
    # Verzeichnis mit dem gebauten Frontend, leer = keins ausliefern
    frontend_dir: Path | None = None
    # Zeitzone für "heute" und den Wochenbeginn
    timezone: str = "Europe/Berlin"
    # Link-Import: Grenzen für das Laden fremder Seiten
    fetch_timeout_s: float = 15.0
    fetch_max_bytes: int = 5_000_000
    # Nur für Tests: private Adressen beim Import erlauben
    allow_private_fetch: bool = False
    # Schlüssel für Zugangsdaten in der Datenbank, etwa Bring! (Abschnitt 11). install.sh erzeugt ihn.
    secret_key: str | None = None
    # KI über das Gateway (Abschnitt 7). Ohne Adresse und Schlüssel läuft die App ohne KI.
    ki_base_url: str | None = None
    # Virtueller Schlüssel des Gateways mit Monatsbudget, nie der Master-Key
    ki_api_key: str | None = None
    # Alias im Gateway, Modellwechsel nur dort
    ki_model: str = "rezept-extraktion"
    ki_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    # output_config = strukturierte Ausgabe mit JSON-Schema. none = nur Prüfung in der App, falls das
    # Gateway das Feld nicht durchreicht (AK-24, Risiko in Abschnitt 13)
    ki_structured: Literal["output_config", "none"] = "output_config"
    ki_timeout_s: float = 180.0

    @property
    def ki_configured(self) -> bool:
        return bool(self.ki_base_url and self.ki_api_key)

    @field_validator("frontend_dir", "secret_key", "ki_base_url", "ki_api_key", mode="before")
    @classmethod
    def _empty_is_none(cls, v):
        return v or None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "delikatessen.sqlite3"

    @property
    def image_dir(self) -> Path:
        return self.data_dir / "bilder"

    @property
    def trusted_proxy_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        nets = []
        for part in self.trusted_proxies.split(","):
            part = part.strip()
            if part:
                nets.append(ipaddress.ip_network(part, strict=False))
        return nets


@lru_cache
def get_settings() -> Settings:
    return Settings()
