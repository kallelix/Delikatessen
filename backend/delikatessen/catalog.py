"""Zutatenkatalog: Normalisierung, Zuordnung und Grundbestand (Abschnitt 4)."""

from __future__ import annotations

import json
from importlib import resources

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Ingredient, IngredientAlias, IngredientGroup, Tag


def normalize(name: str) -> str:
    """Kleinschreibung, einfache Leerzeichen."""
    return " ".join(name.lower().replace(" ", " ").split())


def singular_forms(norm: str) -> list[str]:
    """Mögliche Einzahlformen eines kleingeschriebenen Namens (Tomaten -> tomate, Eier -> ei)."""
    forms = []
    for suffix in ("en", "er", "es", "n", "s", "e"):
        if norm.endswith(suffix) and len(norm) - len(suffix) >= 3:
            forms.append(norm[: -len(suffix)])
    return forms


class Matcher:
    """Ordnet Namen dem Katalog zu: exakter Name, Alias, normalisierte Form. Sonst None."""

    def __init__(self, session: Session):
        self.exact: dict[str, int] = {}
        self.forms: dict[str, int] = {}
        self.names: dict[int, str] = {}
        for ing in session.scalars(select(Ingredient)):
            self.names[ing.id] = ing.name
            n = normalize(ing.name)
            self.exact.setdefault(n, ing.id)
            for a in ing.aliases:
                self.exact.setdefault(a.alias, ing.id)
            for f in singular_forms(n):
                self.forms.setdefault(f, ing.id)

    def match(self, name: str) -> int | None:
        n = normalize(name)
        if not n:
            return None
        if n in self.exact:
            return self.exact[n]
        candidates = singular_forms(n)
        for f in candidates:
            if f in self.exact:
                return self.exact[f]
        if n in self.forms:
            return self.forms[n]
        for f in candidates:
            if f in self.forms:
                return self.forms[f]
        return None


def learn_alias(session: Session, ingredient: Ingredient, name: str) -> None:
    """Merkt sich einen abweichenden Namen als Alias, damit er künftig automatisch passt."""
    n = normalize(name)
    if not n or n == normalize(ingredient.name):
        return
    existing = session.scalar(select(IngredientAlias).where(IngredientAlias.alias == n))
    if existing is None and session.scalar(select(Ingredient).where(Ingredient.name == name)) is None:
        session.add(IngredientAlias(ingredient_id=ingredient.id, alias=n))


def seed(session: Session) -> None:
    """Legt fehlende Einträge des Grundkatalogs an. Vorhandenes bleibt unverändert."""
    data = json.loads(resources.files("delikatessen").joinpath("data/katalog.json").read_text("utf-8"))

    tags = set(session.scalars(select(Tag.name)))
    for t in data["tags"]:
        if t not in tags:
            session.add(Tag(name=t))

    groups = {g.name: g for g in session.scalars(select(IngredientGroup))}
    names = set(session.scalars(select(Ingredient.name)))
    aliases = set(session.scalars(select(IngredientAlias.alias)))
    taken = {normalize(n) for n in names} | aliases
    for group_name, items in data["groups"].items():
        group = groups.get(group_name)
        if group is None:
            group = IngredientGroup(name=group_name)
            session.add(group)
            session.flush()
        for name, unit, alias_list in items:
            if name in names:
                continue
            ing = Ingredient(name=name, group_id=group.id, default_unit=unit)
            session.add(ing)
            session.flush()
            taken.add(normalize(name))
            for a in alias_list:
                na = normalize(a)
                if na not in taken:
                    session.add(IngredientAlias(ingredient_id=ing.id, alias=na))
                    taken.add(na)
    session.commit()
