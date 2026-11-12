"""Einkaufsliste aus dem Plan (F-30 bis F-34, Abschnitt 8)."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .bring import BringClient, Change
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


def _quantity(line: Line) -> str:
    return format_quantity(line.amount, line.unit) if line.kind else ""


def _state(session: Session, week: PlanWeek, lines: list[Line]) -> dict[str, ShoppingItem]:
    """Gespeicherter Zustand je Zeile, auch für Zeilen, die nicht mehr in der Liste stehen."""
    state = {s.key: s for s in session.scalars(select(ShoppingItem).where(ShoppingItem.week_id == week.id))}
    for line in lines:
        if line.key not in state:
            item = ShoppingItem(week_id=week.id, key=line.key)
            session.add(item)
            state[line.key] = item
    session.commit()
    return state


def bring_groups(lines: list[Line], state: dict[str, ShoppingItem]) -> dict[str, tuple[str, list[ShoppingItem]]]:
    """Was in Bring! stehen soll: je Name ein Eintrag mit Mengentext, abgehakte und vorhandene fehlen.

    Bring! kennt jeden Artikel einmal je Liste, deshalb werden gleichnamige Zeilen mit
    nicht umrechenbaren Einheiten zusammengefasst, etwa "400 ml + 1 Becher".
    """
    groups: dict[str, list[Line]] = {}
    for line in lines:
        item = state[line.key]
        if not (item.checked or item.at_home):
            groups.setdefault(line.name, []).append(line)
    return {
        name: (" + ".join(q for q in map(_quantity, members) if q), [state[m.key] for m in members])
        for name, members in groups.items()
    }


def _bring_status(item: ShoppingItem, wanted: tuple[str, str] | None) -> str | None:
    if item.bring_uuid is None:
        return "offen" if wanted else None
    if wanted and (item.bring_name, item.bring_spec) == wanted:
        return "übertragen"
    return "geändert"


def shopping_list(session: Session, week: PlanWeek) -> list[dict]:
    lines = compute_lines(session, week)
    state = _state(session, week, lines)
    wanted = {id(item): (name, spec) for name, (spec, items) in bring_groups(lines, state).items() for item in items}
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
                "quantity": _quantity(line),
                "recipes": line.recipes,
                "checked": item.checked,
                "at_home": item.at_home,
                "bring": _bring_status(item, wanted.get(id(item))),
            }
        )
    return out


def transfer_to_bring(session: Session, week: PlanWeek, client: BringClient, list_uuid: str) -> dict:
    """Überträgt die Liste an Bring! (Abschnitt 8).

    Vorhandene Einträge werden über ihre Kennung aktualisiert statt verdoppelt, auch wenn sie in Bring!
    schon abgehakt sind. Entfernt wird nur, was die App selbst angelegt hat. Erst wenn Bring! die
    Änderung angenommen hat, merkt sich die App die Kennungen. Ein BringError lässt alles unverändert.
    """
    lines = compute_lines(session, week)
    state = _state(session, week, lines)
    groups = bring_groups(lines, state)

    changes: list[Change] = []
    assign: list[tuple[list[ShoppingItem], str, str, str]] = []
    for name, (spec, items) in groups.items():
        uuid = next((i.bring_uuid for i in items if i.bring_uuid and i.bring_name == name), None) or str(uuid4())
        changes.append(Change(uuid=uuid, name=name, spec=spec, op="add"))
        assign.append((items, uuid, name, spec))
    keep = {c.uuid for c in changes}

    gone: dict[str, Change] = {}
    for item in state.values():
        if item.bring_uuid and item.bring_uuid not in keep and item.bring_uuid not in gone:
            # gekauft wird in Bring! abgehakt, alles andere (schon im Haus, aus dem Plan gefallen) entfernt
            op = "complete" if item.checked else "remove"
            gone[item.bring_uuid] = Change(item.bring_uuid, item.bring_name or "", item.bring_spec or "", op)

    client.apply(list_uuid, changes + list(gone.values()))

    for item in state.values():
        if item.bring_uuid in gone:
            item.bring_uuid = item.bring_name = item.bring_spec = None
    for items, uuid, name, spec in assign:
        for item in items:
            item.bring_uuid, item.bring_name, item.bring_spec = uuid, name, spec
    session.commit()
    return {"uebertragen": len(changes), "entfernt": len(gone)}
