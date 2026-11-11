"""Datenbank automatisch auf den neuesten Stand bringen (N-14)."""

from __future__ import annotations

from importlib import resources

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(resources.files("delikatessen") / "migrations"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)
