"""Wochenplan, Bewertungen, Rangliste und Einkaufsliste (F-10 bis F-34)."""

from __future__ import annotations

import random
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .. import appsettings, history, planner
from ..models import Ingredient, Person, PlanSlot, PlanWeek, Rating, Recipe, ShoppingItem
from ..shopping import shopping_list
from .deps import get_db, get_today
from .recipes import image_url, summary
from .schemas import (
    Badge,
    GenerateIn,
    MonthDish,
    NewDish,
    OpenRating,
    PlanOut,
    RankingEntry,
    Rankings,
    RatingIn,
    RecipeSummary,
    ShoppingItemOut,
    ShoppingPatch,
    SlotAdd,
    SlotOut,
    SlotRecipe,
    SlotUpdate,
    UseUpIn,
    UseUpItem,
)

router = APIRouter()

OPEN_RATING_DAYS = 14


def slot_recipe(r: Recipe | None) -> SlotRecipe | None:
    if r is None:
        return None
    return SlotRecipe(id=r.id, title=r.title, image_url=image_url(r.image), duration_min=r.duration_min, size=r.size)


def is_past(week: PlanWeek, today: date) -> bool:
    """Ganz vergangene Wochen sind nur lesbar, Wertungen und "nicht gekocht" bleiben nachtragbar (D-JOUR)."""
    return week.start + timedelta(days=6) < today


def ensure_editable(week: PlanWeek, today: date) -> None:
    if is_past(week, today):
        raise HTTPException(409, "Vergangene Wochen sind nur lesbar. Wertungen lassen sich nachtragen.")


def use_up_out(week: PlanWeek) -> list[UseUpItem]:
    ids = week.use_up or []
    if not ids:
        return []
    names = dict(
        object_session(week).execute(select(Ingredient.id, Ingredient.name).where(Ingredient.id.in_(ids))).all()
    )
    return [UseUpItem(id=i, name=names[i]) for i in ids if i in names]


def plan_out(week: PlanWeek, today: date) -> PlanOut:
    return PlanOut(
        start=week.start,
        end=week.start + timedelta(days=6),
        version=week.version,
        status=week.status,
        readonly=is_past(week, today),
        use_up=use_up_out(week),
        slots=[
            SlotOut(
                id=s.id,
                date=s.date,
                meal=s.meal,
                size=s.size,
                extra=s.extra,
                recipe=slot_recipe(s.recipe),
                pinned=s.pinned,
                cancelled=s.cancelled,
                not_cooked=s.not_cooked,
                reason=s.reason,
                cooked=history.is_cooked(s, today),
                rateable=s.recipe_id is not None and not s.cancelled and s.date <= today,
                ratings={r.person_id: r.value for r in s.ratings},
            )
            for s in week.slots
        ],
    )


def parse_start(start: str, today: date) -> date:
    if start == "aktuell":
        return planner.week_start(today)
    if start == "naechste":
        return planner.week_start(today) + timedelta(days=7)
    try:
        d = date.fromisoformat(start)
    except ValueError as e:
        raise HTTPException(422, "Ungültiges Datum") from e
    if d.weekday() != 5:
        raise HTTPException(422, "Eine Planwoche beginnt am Samstag")
    return d


def load_week(db: Session, start: str, today: date) -> PlanWeek:
    return planner.get_or_create_week(db, parse_start(start, today), appsettings.load(db))


def check_version(week: PlanWeek, version: int | None) -> None:
    """Gleichzeitige Änderungen: die zweite wird mit Hinweis abgelehnt (F-23)."""
    if version is not None and version != week.version:
        raise HTTPException(409, "Der Plan wurde inzwischen geändert. Bitte neu laden.")


def get_slot(week: PlanWeek, slot_id: int) -> PlanSlot:
    for s in week.slots:
        if s.id == slot_id:
            return s
    raise HTTPException(404, "Platz nicht gefunden")


@router.get("/plans/{start}", response_model=PlanOut)
def get_plan(start: str, db: Session = Depends(get_db), today: date = Depends(get_today)):
    return plan_out(load_week(db, start, today), today)


@router.post("/plans/{start}/generate", response_model=PlanOut)
def generate_plan(
    start: str, data: GenerateIn | None = None, db: Session = Depends(get_db), today: date = Depends(get_today)
):
    data = data or GenerateIn()
    week = load_week(db, start, today)
    ensure_editable(week, today)
    check_version(week, data.version)
    rng = random.Random(data.seed) if data.seed is not None else None
    planner.generate(db, week, appsettings.load(db), today, rng)
    return plan_out(week, today)


@router.post("/plans/{start}/slots", response_model=PlanOut, status_code=201)
def add_slots(start: str, data: SlotAdd, db: Session = Depends(get_db), today: date = Depends(get_today)):
    week = load_week(db, start, today)
    ensure_editable(week, today)
    check_version(week, data.version)
    last = data.last or data.first
    if last < data.first:
        raise HTTPException(422, "Das Ende liegt vor dem Anfang")
    planner.add_slots(db, week, data.first, last, data.meal, data.size)
    return plan_out(week, today)


@router.put("/plans/{start}/slots/{slot_id}", response_model=PlanOut)
def update_slot(
    start: str, slot_id: int, data: SlotUpdate, db: Session = Depends(get_db), today: date = Depends(get_today)
):
    week = load_week(db, start, today)
    only_cooked_flag = data.model_dump(exclude_unset=True, exclude={"version", "not_cooked"}) == {}
    if not only_cooked_flag:
        ensure_editable(week, today)
    check_version(week, data.version)
    slot = get_slot(week, slot_id)
    if data.swap_main:
        try:
            planner.swap_main(week, slot)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    if data.recipe_id is not None:
        recipe = db.get(Recipe, data.recipe_id)
        if recipe is None:
            raise HTTPException(404, "Rezept nicht gefunden")
        slot.recipe_id, slot.recipe = recipe.id, recipe
        slot.reason = "selbst gewählt"
        slot.pinned = True if data.pinned is None else data.pinned
    if data.clear_recipe:
        slot.recipe_id, slot.recipe, slot.reason, slot.pinned = None, None, None, False
    if data.pinned is not None and data.recipe_id is None:
        slot.pinned = data.pinned
    if data.cancelled is not None:
        slot.cancelled = data.cancelled
        if data.cancelled:
            slot.pinned = False
    if data.not_cooked is not None:
        slot.not_cooked = data.not_cooked
    week.version += 1
    db.commit()
    return plan_out(week, today)


@router.delete("/plans/{start}/slots/{slot_id}", response_model=PlanOut)
def delete_slot(
    start: str, slot_id: int, version: int, db: Session = Depends(get_db), today: date = Depends(get_today)
):
    week = load_week(db, start, today)
    ensure_editable(week, today)
    check_version(week, version)
    slot = get_slot(week, slot_id)
    if not slot.extra:
        raise HTTPException(422, "Nur Zusatzplätze lassen sich entfernen. Sonst: Essen entfällt.")
    week.slots.remove(slot)
    week.version += 1
    db.commit()
    return plan_out(week, today)


@router.put("/plans/{start}/use-up", response_model=PlanOut)
def put_use_up(start: str, data: UseUpIn, db: Session = Depends(get_db), today: date = Depends(get_today)):
    """ "Diese Woche verbrauchen" aus der Zutatensuche (D-ZUT). Wirkt beim nächsten Erzeugen und Neu-Vorschlag."""
    week = load_week(db, start, today)
    ensure_editable(week, today)
    check_version(week, data.version)
    known = set(db.scalars(select(Ingredient.id).where(Ingredient.id.in_(data.ingredient_ids))))
    week.use_up = [i for i in dict.fromkeys(data.ingredient_ids) if i in known]
    week.version += 1
    db.commit()
    return plan_out(week, today)


@router.post("/plans/{start}/slots/{slot_id}/suggest", response_model=PlanOut)
def suggest_slot(
    start: str, slot_id: int, data: GenerateIn, db: Session = Depends(get_db), today: date = Depends(get_today)
):
    week = load_week(db, start, today)
    ensure_editable(week, today)
    check_version(week, data.version)
    slot = get_slot(week, slot_id)
    rng = random.Random(data.seed) if data.seed is not None else None
    planner.suggest(db, week, slot, appsettings.load(db), today, rng)
    return plan_out(week, today)


@router.get("/plans/{start}/slots/{slot_id}/candidates", response_model=list[RecipeSummary])
def slot_candidates(start: str, slot_id: int, db: Session = Depends(get_db), today: date = Depends(get_today)):
    """Für "Rezept wählen": nur Rezepte, die die harten Regeln erfüllen, passende Größe zuerst (F-21)."""
    week = load_week(db, start, today)
    slot = get_slot(week, slot_id)
    ctx = planner.build_context(db, appsettings.load(db), today)
    recipes = sorted((c.recipe for c in ctx.candidates), key=lambda r: (r.size != slot.size, r.title.lower()))
    return [summary(r) for r in recipes]


# --- Bewertungen -----------------------------------------------------------------------


@router.put("/slots/{slot_id}/ratings/{person_id}", response_model=dict[int, float])
def rate(slot_id: int, person_id: int, data: RatingIn, db: Session = Depends(get_db), today: date = Depends(get_today)):
    """Eine Wertung je Person und Kochereignis, später änderbar. Auch stellvertretend (F-10)."""
    slot = db.get(PlanSlot, slot_id)
    if slot is None:
        raise HTTPException(404, "Platz nicht gefunden")
    if db.get(Person, person_id) is None:
        raise HTTPException(404, "Person nicht gefunden")
    if slot.recipe_id is None or slot.cancelled or slot.date > today:
        raise HTTPException(422, "Bewerten geht erst, wenn das Essen dran war")
    rating = db.scalar(select(Rating).where(Rating.slot_id == slot_id, Rating.person_id == person_id))
    if data.value is None:
        if rating is not None:
            db.delete(rating)
    elif rating is None:
        db.add(Rating(slot_id=slot_id, person_id=person_id, value=data.value))
    else:
        rating.value = data.value
    if data.value is not None and slot.not_cooked:
        slot.not_cooked = False
    db.commit()
    db.refresh(slot)
    return {r.person_id: r.value for r in slot.ratings}


@router.get("/ratings/open", response_model=list[OpenRating])
def open_ratings(db: Session = Depends(get_db), today: date = Depends(get_today)):
    """Gekochte Essen der letzten zwei Wochen, für die noch Wertungen fehlen."""
    persons = db.scalars(select(Person).where(Person.active.is_(True))).all()
    if not persons:
        return []
    slots = db.scalars(
        select(PlanSlot)
        .where(
            PlanSlot.recipe_id.is_not(None),
            PlanSlot.cancelled.is_(False),
            PlanSlot.not_cooked.is_(False),
            PlanSlot.date <= today,
            PlanSlot.date > today - timedelta(days=OPEN_RATING_DAYS),
        )
        .order_by(PlanSlot.date.desc(), PlanSlot.meal)
    ).all()
    out = []
    for s in slots:
        rated = {r.person_id for r in s.ratings}
        missing = [p.id for p in persons if p.id not in rated]
        if missing:
            out.append(
                OpenRating(
                    slot_id=s.id, date=s.date, meal=s.meal, recipe=slot_recipe(s.recipe), missing_person_ids=missing
                )
            )
    return out


@router.get("/rankings", response_model=Rankings)
def rankings(db: Session = Depends(get_db), today: date = Depends(get_today)):
    """Rangliste nach Favoritenwert (F-12) und "hatten wir lange nicht" (D-LANG)."""
    stats = history.collect(db, today)
    entries = []
    for r in db.scalars(select(Recipe).where(Recipe.excluded.is_(False))):
        st = stats.get(r.id)
        entries.append(
            (
                r,
                RankingEntry(
                    recipe=summary(r),
                    favorite_score=round(history.favorite_score(st, r.favorite), 3),
                    ratings=len(st.ratings) if st else 0,
                    cooked_count=len(st.cooked) if st else 0,
                    last_cooked=st.last_cooked if st else None,
                ),
                history.long_not_eaten(st, today),
            )
        )
    ranking = sorted((e for _, e, _ in entries), key=lambda e: (-e.favorite_score, -e.cooked_count, e.recipe.title))
    # nur schon gekochte Gerichte, die lange her sind und gut ankamen
    lang = [(lval, e) for _, e, lval in entries if e.cooked_count > 0 and lval >= 0.5 and e.favorite_score >= 0.5]
    lang.sort(key=lambda x: (-(x[0] + x[1].favorite_score), x[1].recipe.title))
    recipes = {r.id: r for r, _, _ in entries}
    return Rankings(
        ranking=ranking,
        long_not_eaten=[e for _, e in lang[:5]],
        essen_des_monats=dish_of_month(db, today, recipes),
        neu_ausprobiert=[
            NewDish(recipe=summary(recipes[rid]), erstmals=first)
            for rid, first in sorted(first_cooked(stats).items(), key=lambda x: (x[1], x[0]), reverse=True)
            if rid in recipes and (first.year, first.month) == (today.year, today.month)
        ],
        abzeichen=badges(len([rid for rid in first_cooked(stats) if rid in recipes])),
    )


MIN_MONTH_RATINGS = 2
BADGES = [
    (1, "Erster Versuch", "das erste Gericht gekocht"),
    (5, "Neugierig", "5 verschiedene Gerichte ausprobiert"),
    (10, "Entdecker", "10 verschiedene Gerichte ausprobiert"),
    (25, "Feinschmecker", "25 verschiedene Gerichte ausprobiert"),
    (50, "Weltenbummler", "50 verschiedene Gerichte ausprobiert"),
    (100, "Delikatessen-Profi", "100 verschiedene Gerichte ausprobiert"),
]


def first_cooked(stats: dict[int, history.RecipeStats]) -> dict[int, date]:
    return {rid: min(st.cooked) for rid, st in stats.items() if st.cooked}


def badges(tried: int) -> list[Badge]:
    """Abzeichen der ganzen Familie für neu ausprobierte Gerichte, ohne Vergleich zwischen Personen (D-RANK)."""
    return [
        Badge(name=n, beschreibung=d, ziel=goal, stand=min(tried, goal), erreicht=tried >= goal)
        for goal, n, d in BADGES
    ]


def dish_of_month(db: Session, today: date, recipes: dict[int, Recipe]) -> MonthDish | None:
    """Bestes Mittel der Wertungen im Monat, ab zwei Wertungen. Steht im laufenden Monat noch keins fest,
    gilt der Vormonat."""
    first = today.replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    for start, end, running in ((first, today, True), (prev, first - timedelta(days=1), False)):
        rows = db.execute(
            select(PlanSlot.recipe_id, Rating.value)
            .join(Rating, Rating.slot_id == PlanSlot.id)
            .where(
                PlanSlot.cancelled.is_(False),
                PlanSlot.not_cooked.is_(False),
                PlanSlot.date >= start,
                PlanSlot.date <= end,
            )
        ).all()
        values: dict[int, list[float]] = {}
        for rid, v in rows:
            if rid in recipes:
                values.setdefault(rid, []).append(v)
        ok = [(sum(v) / len(v), len(v), rid) for rid, v in values.items() if len(v) >= MIN_MONTH_RATINGS]
        if ok:
            mean, count, rid = max(ok, key=lambda x: (x[0], x[1], -x[2]))
            return MonthDish(
                recipe=summary(recipes[rid]),
                monat=start.strftime("%Y-%m"),
                mittel=round(mean, 3),
                wertungen=count,
                laufend=running,
            )
    return None


# --- Einkauf ---------------------------------------------------------------------------


@router.get("/plans/{start}/shopping", response_model=list[ShoppingItemOut])
def get_shopping(start: str, db: Session = Depends(get_db), today: date = Depends(get_today)):
    return shopping_list(db, load_week(db, start, today))


@router.patch("/shopping/items/{item_id}", response_model=ShoppingItemOut | None)
def patch_shopping(item_id: int, data: ShoppingPatch, db: Session = Depends(get_db)):
    item = db.get(ShoppingItem, item_id)
    if item is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    if data.checked is not None:
        item.checked = data.checked
    if data.at_home is not None:
        item.at_home = data.at_home
    db.commit()
    week = db.get(PlanWeek, item.week_id)
    for entry in shopping_list(db, week):
        if entry["id"] == item_id:
            return entry
    return None
