"""Wochenplan: Raster, Algorithmus und Änderungen (F-20 bis F-27, Abschnitt 6)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import history
from .appsettings import AppSettings
from .models import Person, PlanSlot, PlanWeek, Recipe

TOP_N = 5
SIZE_LABEL = {"haupt": "Hauptmahlzeit", "klein": "kleine Mahlzeit"}


def week_start(d: date) -> date:
    """Die Planwoche beginnt am Samstag (F-24)."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


def standard_slots(start: date, settings: AppSettings) -> list[PlanSlot]:
    slots = []
    for i in range(7):
        d = start + timedelta(days=i)
        meals = settings.grid.get(d.weekday(), [])
        weekend = d.weekday() >= 5
        for meal in meals:
            if weekend:
                # je Wochenendtag genau eine Hauptmahlzeit (F-26)
                size = "haupt" if len(meals) == 1 or meal == settings.weekend_main else "klein"
            else:
                size = "haupt" if meal == "abend" or len(meals) == 1 else "klein"
            slots.append(PlanSlot(date=d, meal=meal, size=size))
    return slots


def get_or_create_week(session: Session, start: date, settings: AppSettings) -> PlanWeek:
    week = session.scalar(select(PlanWeek).where(PlanWeek.start == start))
    if week is None:
        week = PlanWeek(start=start, version=1)
        week.slots = standard_slots(start, settings)
        session.add(week)
        session.commit()
    return week


# --- Kandidaten und Punkte ------------------------------------------------------------


@dataclass
class Candidate:
    recipe: Recipe
    ingredient_ids: set[int]
    group_ids: set[int]
    tag_ids: set[int]


@dataclass
class Context:
    settings: AppSettings
    today: date
    stats: dict[int, history.RecipeStats]
    all_recipes: list[Recipe]
    candidates: list[Candidate]  # planbar, nicht ausgeschlossen, ohne No-go
    nogo_blocked: set[int]
    # Zutaten, die diese Woche verbraucht werden sollen, und die davon schon abgedeckten (D-ZUT)
    use_up: set[int] = field(default_factory=set)
    covered: set[int] = field(default_factory=set)

    def cover(self, c: Candidate) -> None:
        self.covered |= c.ingredient_ids & self.use_up


def build_context(session: Session, settings: AppSettings, today: date, use_up=()) -> Context:
    persons = session.scalars(select(Person).where(Person.active.is_(True))).all()
    nogo_ing = {n.ingredient_id for p in persons for n in p.nogos if n.ingredient_id}
    nogo_grp = {n.group_id for p in persons for n in p.nogos if n.group_id}
    recipes = session.scalars(select(Recipe)).all()
    cands = []
    blocked = set()
    for r in recipes:
        if r.excluded or not r.plannable:
            continue
        ing_ids = {ri.ingredient_id for ri in r.ingredients if ri.ingredient_id}
        grp_ids = {ri.ingredient.group_id for ri in r.ingredients if ri.ingredient and ri.ingredient.group_id}
        if ing_ids & nogo_ing or grp_ids & nogo_grp:
            blocked.add(r.id)
            continue
        cands.append(Candidate(r, ing_ids, grp_ids, {t.id for t in r.tags}))
    return Context(settings, today, history.collect(session, today), list(recipes), cands, blocked, set(use_up or ()))


def time_fits(recipe: Recipe, slot: PlanSlot, settings: AppSettings) -> float:
    """T: 1, wenn die Dauer zum Tageslimit passt. Ohne Limit passt alles, ohne Dauer nur ohne Limit."""
    limit = settings.time_limits.get(slot.date.weekday())
    if limit is None:
        return 1.0
    return 1.0 if recipe.duration_min is not None and recipe.duration_min <= limit else 0.0


def repetition(c: Candidate, chosen: list[Candidate]) -> float:
    """A: 1 bei gleichem Rezept, sonst Anteil der eigenen Tags, die schon gewählte Gerichte tragen."""
    if any(o.recipe.id == c.recipe.id for o in chosen):
        return 1.0
    if not c.tag_ids:
        return 0.0
    used = set().union(*(o.tag_ids for o in chosen)) if chosen else set()
    return len(c.tag_ids & used) / len(c.tag_ids)


@dataclass
class Scored:
    cand: Candidate
    score: float
    reason: str


def use_up_share(c: Candidate, ctx: Context) -> float:
    """V: Anteil der noch nicht abgedeckten Verbrauchen-Zutaten, die das Rezept enthält."""
    remaining = ctx.use_up - ctx.covered
    return len(c.ingredient_ids & remaining) / len(remaining) if remaining else 0.0


def score(c: Candidate, slot: PlanSlot, chosen: list[Candidate], ctx: Context) -> Scored:
    w = ctx.settings.weights
    st = ctx.stats.get(c.recipe.id)
    f = history.favorite_score(st, c.recipe.favorite)
    lval = history.long_not_eaten(st, slot.date)
    t = time_fits(c.recipe, slot, ctx.settings)
    a = repetition(c, chosen)
    v = use_up_share(c, ctx)
    n = 0.0 if st and st.cooked else 1.0
    s = w.F * f + w.L * lval + w.T * t - w.A * a + w.V * v + w.N * n
    parts = {"F": w.F * f, "L": w.L * lval, "T": w.T * t, "V": w.V * v, "N": w.N * n}
    main = max(parts, key=parts.get)
    if main == "V":
        remaining = ctx.use_up - ctx.covered
        names = sorted({ri.ingredient.name for ri in c.recipe.ingredients if ri.ingredient_id in remaining})
        reason = f"verbraucht {', '.join(names)}"
    elif main == "N":
        reason = "mal was Neues"
    elif main == "F":
        reason = "Favorit" if c.recipe.favorite else "Lieblingsessen"
    elif main == "L":
        reason = "noch nie gekocht" if not (st and st.cooked) else "lange nicht gegessen"
    else:
        reason = "schnell gemacht"
    return Scored(c, s, reason)


def empty_reason(slot: PlanSlot, ctx: Context, rejected: set[int]) -> str:
    label = SIZE_LABEL[slot.size]
    same_size = [r for r in ctx.all_recipes if r.size == slot.size and not r.excluded]
    if not same_size:
        return f"Keine {label} im Rezeptbuch"
    if not any(r.plannable for r in same_size):
        return f"Jede {label} hat noch nicht zugeordnete Zutaten"
    if all(r.id in ctx.nogo_blocked for r in same_size if r.plannable):
        return f"Jede passende {label} enthält ein No-go"
    if rejected:
        return "Alle passenden Rezepte wurden diese Woche verworfen"
    return f"Keine passende {label}"


def pick(
    slot: PlanSlot, pool: list[Candidate], chosen: list[Candidate], ctx: Context, rng: random.Random
) -> Scored | None:
    if not pool:
        return None
    scored = sorted((score(c, slot, chosen, ctx) for c in pool), key=lambda s: (-s.score, s.cand.recipe.id))
    top = scored[:TOP_N]
    weights = [max(s.score, 0.01) for s in top]
    return rng.choices(top, weights=weights, k=1)[0]


def week_rejected(week: PlanWeek) -> set[int]:
    return {rid for s in week.slots for rid in (s.rejected or [])}


def generate(
    session: Session, week: PlanWeek, settings: AppSettings, today: date, rng: random.Random | None = None
) -> PlanWeek:
    """Füllt alle offenen Plätze neu. Fixierte und entfallene Plätze bleiben unverändert (F-21)."""
    rng = rng or random.Random()
    ctx = build_context(session, settings, today, week.use_up)
    by_id = {c.recipe.id: c for c in ctx.candidates}
    rejected = week_rejected(week)

    chosen: list[Candidate] = []
    open_slots = []
    for slot in week.slots:
        if slot.pinned or slot.cancelled:
            if slot.recipe_id in by_id and not slot.cancelled:
                chosen.append(by_id[slot.recipe_id])
                ctx.cover(by_id[slot.recipe_id])
            continue
        slot.recipe_id = None
        slot.recipe = None
        slot.reason = None
        open_slots.append(slot)

    def pool_for(slot: PlanSlot) -> list[Candidate]:
        pool = [c for c in ctx.candidates if c.recipe.size == slot.size]
        fresh = [c for c in pool if c.recipe.id not in rejected]
        return fresh or pool

    # knappe Plätze zuerst
    open_slots.sort(key=lambda s: (len(pool_for(s)), s.date, s.meal != "mittag"))
    for slot in open_slots:
        result = pick(slot, pool_for(slot), chosen, ctx, rng)
        if result is None:
            slot.reason = empty_reason(slot, ctx, rejected)
            continue
        slot.recipe_id = result.cand.recipe.id
        slot.recipe = result.cand.recipe
        slot.reason = result.reason
        chosen.append(result.cand)
        ctx.cover(result.cand)
    week.version += 1
    session.commit()
    return week


def suggest(
    session: Session,
    week: PlanWeek,
    slot: PlanSlot,
    settings: AppSettings,
    today: date,
    rng: random.Random | None = None,
) -> PlanWeek:
    """Neuer Vorschlag: nächster Kandidat ohne die diese Woche schon verworfenen Rezepte (F-21)."""
    rng = rng or random.Random()
    if slot.recipe_id is not None:
        slot.rejected = [*(slot.rejected or []), slot.recipe_id]
    ctx = build_context(session, settings, today, week.use_up)
    rejected = week_rejected(week)
    by_id = {c.recipe.id: c for c in ctx.candidates}
    chosen = [by_id[s.recipe_id] for s in week.slots if s.id != slot.id and not s.cancelled and s.recipe_id in by_id]
    for c in chosen:
        ctx.cover(c)
    pool = [c for c in ctx.candidates if c.recipe.size == slot.size and c.recipe.id not in rejected]
    result = pick(slot, pool, chosen, ctx, rng)
    slot.pinned = False
    if result is None:
        slot.recipe_id = None
        slot.recipe = None
        slot.reason = empty_reason(slot, ctx, rejected)
    else:
        slot.recipe_id = result.cand.recipe.id
        slot.recipe = result.cand.recipe
        slot.reason = result.reason
    week.version += 1
    session.commit()
    return week


def add_slots(session: Session, week: PlanWeek, first: date, last: date, meal: str, size: str) -> PlanWeek:
    """Zusatzplätze für einen Tag oder Zeitraum, nur in dieser Woche (F-20)."""
    end = week.start + timedelta(days=6)
    first, last = max(first, week.start), min(last, end)
    existing = {(s.date, s.meal) for s in week.slots}
    d = first
    while d <= last:
        if (d, meal) not in existing:
            week.slots.append(PlanSlot(date=d, meal=meal, size=size, extra=True))
        d += timedelta(days=1)
    week.version += 1
    session.commit()
    session.refresh(week)
    return week


def swap_main(week: PlanWeek, slot: PlanSlot) -> None:
    """Tauscht am Wochenende, welche Mahlzeit des Tages die große ist."""
    same_day = [s for s in week.slots if s.date == slot.date and s.id != slot.id]
    if len(same_day) != 1:
        raise ValueError("Am Tag gibt es keine zweite Mahlzeit zum Tauschen")
    other = same_day[0]
    slot.size, other.size = other.size, slot.size
    for s in (slot, other):
        if s.recipe is not None and s.recipe.size != s.size and not s.pinned:
            s.recipe_id = None
            s.recipe = None
            s.reason = "Größe geändert, bitte neu vorschlagen"
