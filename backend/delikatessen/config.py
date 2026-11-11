"""Konfiguration aus Umgebungsvariablen (Präfix DELIKATESSEN_) oder einer env-Datei (N-16)."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path

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

    @field_validator("frontend_dir", mode="before")
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
