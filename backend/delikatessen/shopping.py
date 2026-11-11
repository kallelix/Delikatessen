"""Einkaufsliste aus dem Plan (F-30 bis F-34, Abschnitt 8)."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import normalize
from .models import Person, PlanWeek, ShoppingItem
from .units import UNITS, format_quantity, humanize_base, round_amount, to_base, unit_kind

OTHER_GROUP = "Sonstiges"


@dataclass
class Line:
    key: str
    name: str
    group: str
    kind: str | None  # masse, volumen, sonstige Einheit oder None (ohne Menge)
    amount: float = 0.0
    unit: str | None = None
    recipes: list[str] = field(default_factory=list)


def _key(ingredient_part: str, kind: str | None) -> str:
    raw = f"{ingredient_part}|{kind or '-'}"
    if len(raw) <= 60:
        return raw
    return hashlib.sha1(raw.encode()).hexdigest()


def compute_lines(session: Session, week: PlanWeek) -> list[Line]:
    persons = session.scalars(select(Person).where(Person.active.is_(True))).all()
    factor_sum = sum(p.portion_factor for p in persons)

    lines: dict[str, Line] = {}
    for slot in week.slots:
        recipe = slot.recipe
        # entfallene und nicht gekochte Plätze zählen nicht (Abschnitt 8, Regel 5)
        if recipe is None or slot.cancelled or slot.not_cooked:
            continue
        mult = (factor_sum or recipe.servings) / recipe.servings
        for ri in recipe.ingredients:
            if ri.ingredient is not None:
                ing_part, name = f"i{ri.ingredient_id}", ri.ingredient.name
                group = ri.ingredient.group.name if ri.ingredient.group else OTHER_GROUP
            else:
                ing_part, name, group = f"n{normalize(ri.name)}", ri.name, OTHER_GROUP
            if ri.amount is None:
                kind = None
            else:
                kind = unit_kind(ri.unit) or "Stück"
            key = _key(ing_part, kind)
            line = lines.get(key)
            if line is None:
                line = lines[key] = Line(key=key, name=name, group=group, kind=kind)
            if ri.amount is not None:
                if ri.unit in UNITS:
                    line.amount += to_base(ri.amount * mult, ri.unit)
                else:
                    line.amount += ri.amount * mult
                    line.unit = ri.unit or "Stück"
            if recipe.title not in line.recipes:
                line.recipes.append(recipe.title)

    for line in lines.values():
        if line.kind in ("masse", "volumen"):
            line.amount, line.unit = humanize_base(line.amount, line.kind)
        elif line.unit == "Stück":
            # halbe Äpfel gibt es nicht zu kaufen
            line.amount = float(math.ceil(line.amount - 1e-9))
        elif line.kind is not None:
            line.amount = round_amount(line.amount, line.unit)
    return sorted(lines.values(), key=lambda line: (line.group == OTHER_GROUP, line.group, line.name.lower()))


def shopping_list(session: Session, week: PlanWeek) -> list[dict]:
    lines = compute_lines(session, week)
    state = {s.key: s for s in session.scalars(select(ShoppingItem).where(ShoppingItem.week_id == week.id))}
    for line in lines:
        if line.key not in state:
            item = ShoppingItem(week_id=week.id, key=line.key)
            session.add(item)
            state[line.key] = item
    session.commit()
    out = []
    for line in lines:
        item = state[line.key]
        out.append(
            {
                "id": item.id,
                "name": line.name,
                "group": line.group,
                "amount": line.amount if line.kind else None,
                "unit": line.unit if line.kind else None,
                "quantity": format_quantity(line.amount, line.unit) if line.kind else "",
                "recipes": line.recipes,
                "checked": item.checked,
                "at_home": item.at_home,
            }
        )
    return out
