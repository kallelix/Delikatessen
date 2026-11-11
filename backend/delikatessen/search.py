"""Volltextsuche über Titel und Zutaten mit SQLite FTS5 (F-03)."""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import Recipe


def index_recipe(session: Session, recipe: Recipe) -> None:
    names = " ".join(f"{ri.name} {ri.ingredient.name if ri.ingredient else ''}" for ri in recipe.ingredients)
    session.execute(text("DELETE FROM recipe_fts WHERE rowid = :id"), {"id": recipe.id})
    session.execute(
        text("INSERT INTO recipe_fts(rowid, title, zutaten) VALUES (:id, :t, :z)"),
        {"id": recipe.id, "t": recipe.title, "z": names},
    )


def remove_recipe(session: Session, recipe_id: int) -> None:
    session.execute(text("DELETE FROM recipe_fts WHERE rowid = :id"), {"id": recipe_id})


def search_ids(session: Session, query: str) -> list[int]:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    if not tokens:
        return []
    match = " AND ".join(f'"{t}"*' for t in tokens)
    rows = session.execute(text("SELECT rowid FROM recipe_fts WHERE recipe_fts MATCH :m ORDER BY rank"), {"m": match})
    return [r[0] for r in rows]
