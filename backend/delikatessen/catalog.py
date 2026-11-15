"""Zutatenkatalog: Normalisierung, Zuordnung und Grundbestand (Abschnitt 4)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Ingredient, IngredientAlias, IngredientGroup, IngredientUnitWeight, Tag
from .units import ALL_UNITS, COUNT_UNITS, normalize_unit


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


# --- Grundkatalog aus katalog.yml -------------------------------------------------------------

FOOD_GROUPS = (
    "Gemüse",
    "Obst",
    "Hülsenfrüchte",
    "Nüsse",
    "Kartoffeln",
    "Getreide",
    "Milch",
    "Fisch",
    "Fleisch",
    "Wurst",
    "Eier",
    "Fett",
    "Sonstiges",
)
# Kategorien, deren Zutaten eine Saisonangabe brauchen (AK-30)
SEASON_CATEGORIES = ("Gemüse", "Obst", "Kräuter")
_YEAR_ROUND = "ganzjährig"


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    """Eine Zutat aus katalog.yml, so wie sie in die Datenbank kommt."""

    name: str
    category: str
    unit: str
    aliases: tuple[str, ...]
    food_group: str
    weights: dict[str, float]
    density: float | None
    season_months: list[int] | None
    season_given: bool  # Monate oder ein Grund für „ganzjährig“ stehen in der Datei

    def applied(self) -> dict:
        """Stand, der nach dem Abgleich an der Zutat gemerkt wird."""
        return {
            "default_unit": self.unit,
            "aliases": sorted(normalize(a) for a in self.aliases),
            "food_group": self.food_group,
            "density": self.density,
            "season_months": self.season_months,
            "weights": self.weights,
        }


@dataclass(frozen=True)
class Catalog:
    tags: tuple[str, ...]
    category_groups: dict[str, str]
    entries: dict[str, Entry]


def parse_season(value: object) -> list[int] | None:
    """ "4-6" oder "1-3, 7-12" -> Monate; "10-2" läuft über den Jahreswechsel; "ganzjährig (...)" -> None."""
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"Saison {value!r} ist keine Monatsangabe")
    text = value.strip()
    if text.startswith(_YEAR_ROUND):
        return None
    months: set[int] = set()
    for part in text.split(","):
        bounds = [p.strip() for p in part.split("-")]
        if len(bounds) not in (1, 2) or not all(b.isdigit() for b in bounds):
            raise CatalogError(f"Saison {value!r}: „{part.strip()}“ ist kein Monat oder Bereich")
        a, b = int(bounds[0]), int(bounds[-1])
        if not (1 <= a <= 12 and 1 <= b <= 12):
            raise CatalogError(f"Saison {value!r}: Monate gehen von 1 bis 12")
        m = a
        months.add(m)
        while m != b:
            m = m % 12 + 1
            months.add(m)
    return sorted(months)


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise CatalogError(f"{what}: {value!r} ist keine positive Zahl")
    return float(value)


def parse_catalog(text: str) -> Catalog:
    data = yaml.safe_load(text)
    tags = tuple(data.get("tags") or [])
    category_groups: dict[str, str] = {}
    entries: dict[str, Entry] = {}
    for cname, cat in (data.get("kategorien") or {}).items():
        cgroup = cat.get("gruppe")
        if cgroup not in FOOD_GROUPS:
            raise CatalogError(f"Kategorie {cname}: Gruppe {cgroup!r} ist unbekannt")
        category_groups[cname] = cgroup
        for name, item in (cat.get("zutaten") or {}).items():
            where = f"{cname} › {name}"
            item = item or {}
            unknown = set(item) - {"einheit", "aliasse", "gruppe", "gewicht", "dichte", "saison"}
            if unknown:
                raise CatalogError(f"{where}: unbekannte Felder {sorted(unknown)}")
            if name in entries:
                raise CatalogError(f"{where}: steht doppelt im Katalog")
            unit = normalize_unit(item.get("einheit") or "")
            if unit not in ALL_UNITS:
                raise CatalogError(f"{where}: Einheit {item.get('einheit')!r} ist unbekannt")
            group = item.get("gruppe", cgroup)
            if group not in FOOD_GROUPS:
                raise CatalogError(f"{where}: Gruppe {group!r} ist unbekannt")
            weights: dict[str, float] = {}
            for u, g in (item.get("gewicht") or {}).items():
                nu = normalize_unit(str(u))
                if nu not in COUNT_UNITS:
                    raise CatalogError(f"{where}: Gewicht nur für Zähl-Einheiten wie Stück, nicht für {u!r}")
                weights[nu] = _number(g, f"{where} Gewicht {u}")
            density = _number(item["dichte"], f"{where} Dichte") if "dichte" in item else None
            season = parse_season(item["saison"]) if "saison" in item else None
            entries[name] = Entry(
                name=name,
                category=cname,
                unit=unit,
                aliases=tuple(item.get("aliasse") or []),
                food_group=group,
                weights=weights,
                density=density,
                season_months=season,
                season_given="saison" in item,
            )
    return Catalog(tags=tags, category_groups=category_groups, entries=entries)


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    return parse_catalog(resources.files("delikatessen").joinpath("data/katalog.yml").read_text("utf-8"))


def default_food_group(category: str | None) -> str | None:
    """Gruppe einer neuen Zutat aus ihrer Katalog-Kategorie."""
    return load_catalog().category_groups.get(category) if category else None


def _sync_entry(session: Session, ing: Ingredient, entry: Entry, taken: set[str]) -> None:
    """Dreiwege-Abgleich: Ein Wert aus der Datei kommt nur in die Datenbank, wenn er sich in der Datei seit dem
    letzten Abgleich geändert hat. So bleiben Änderungen der Familie stehen, und Korrekturen im Katalog kommen
    trotzdem mit dem nächsten Update an."""
    new = entry.applied()
    old = ing.catalog_applied or {}
    for key, attr in (
        ("default_unit", "default_unit"),
        ("food_group", "food_group"),
        ("density", "density"),
        ("season_months", "season_months"),
    ):
        if new[key] != old.get(key):
            setattr(ing, attr, new[key])

    old_weights = old.get("weights") or {}
    rows = {w.unit: w for w in ing.weights}
    for unit, grams in new["weights"].items():
        if grams == old_weights.get(unit):
            continue
        if unit in rows:
            rows[unit].grams = grams
        else:
            ing.weights.append(IngredientUnitWeight(unit=unit, grams=grams))
    for unit, grams in old_weights.items():
        # aus der Datei entfernt: weg, außer die Familie hat den Wert inzwischen geändert
        if unit not in new["weights"] and unit in rows and rows[unit].grams == grams:
            ing.weights.remove(rows[unit])

    for alias in set(new["aliases"]) - set(old.get("aliases") or []):
        if alias not in taken:
            ing.aliases.append(IngredientAlias(alias=alias))
            taken.add(alias)
    ing.catalog_applied = new


def seed(session: Session) -> None:
    """Gleicht die Datenbank mit katalog.yml ab: legt Fehlendes an und übernimmt geänderte Werte (_sync_entry)."""
    cat = load_catalog()

    tags = set(session.scalars(select(Tag.name)))
    for t in cat.tags:
        if t not in tags:
            session.add(Tag(name=t))

    groups = {g.name: g for g in session.scalars(select(IngredientGroup))}
    for cname in cat.category_groups:
        if cname not in groups:
            groups[cname] = IngredientGroup(name=cname)
            session.add(groups[cname])
    session.flush()

    existing = {i.name: i for i in session.scalars(select(Ingredient))}
    taken = {normalize(n) for n in existing} | set(session.scalars(select(IngredientAlias.alias)))
    for entry in cat.entries.values():
        ing = existing.get(entry.name)
        if ing is None:
            ing = Ingredient(name=entry.name, group_id=groups[entry.category].id)
            session.add(ing)
            taken.add(normalize(entry.name))
        _sync_entry(session, ing, entry, taken)

    # eigene Zutaten der Familie: Gruppe aus der Kategorie, solange keine gesetzt ist
    for ing in existing.values():
        if ing.name not in cat.entries and ing.food_group is None and ing.group is not None:
            ing.food_group = cat.category_groups.get(ing.group.name)
    session.commit()
