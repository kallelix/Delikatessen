"""Entdecken und Erinnern: Suche nach Zutaten (D-ZUT) und Journal vergangener Essen (D-JOUR)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from ..models import Ingredient, PlanSlot, PlanWeek, Recipe, RecipeIngredient
from .deps import get_db, get_today
from .plans import slot_recipe
from .recipes import summary
from .schemas import Meal, RecipeSummary, SlotRecipe

router = APIRouter()

MAX_SELECTED = 30
MAX_HISTORY = 300


class IngredientHit(BaseModel):
    recipe: RecipeSummary
    treffer: list[str]  # gewählte Zutaten, die das Rezept enthält
    fehlend: int  # Zutaten des Rezepts, die nicht gewählt sind
    anteil: float  # Anteil der Zutaten des Rezepts, die abgedeckt sind


@router.get("/search/by-ingredients", response_model=list[IngredientHit])
def by_ingredients(ids: list[int] = Query(default=[], max_length=MAX_SELECTED), db: Session = Depends(get_db)):
    """Rezepte zu den gewählten Zutaten, sortiert nach dem Anteil abgedeckter Zutaten (D-ZUT)."""
    chosen = set(ids)
    if not chosen:
        return []
    recipe_ids = select(RecipeIngredient.recipe_id).where(RecipeIngredient.ingredient_id.in_(chosen))
    hits = []
    for r in db.scalars(select(Recipe).where(Recipe.id.in_(recipe_ids), Recipe.excluded.is_(False))):
        total = len(r.ingredients)
        found = sorted({ri.ingredient.name for ri in r.ingredients if ri.ingredient_id in chosen and ri.ingredient})
        covered = sum(1 for ri in r.ingredients if ri.ingredient_id in chosen)
        hits.append(
            IngredientHit(
                recipe=summary(r),
                treffer=found,
                fehlend=total - covered,
                anteil=round(covered / total, 3) if total else 0.0,
            )
        )
    hits.sort(key=lambda h: (-h.anteil, -len(h.treffer), h.recipe.title.lower()))
    return hits


class HistoryEntry(BaseModel):
    slot_id: int
    date: date
    meal: Meal
    week_start: date
    status: Literal["gekocht", "entfallen"]
    recipe: SlotRecipe | None
    ratings: dict[int, float]
    mittel: float | None


RATING_BANDS = {
    "lecker": lambda m: m is not None and m >= 0.75,
    "okay": lambda m: m is not None and 0.25 <= m < 0.75,
    "mies": lambda m: m is not None and m < 0.25,
    "ohne": lambda m: m is None,
}


@router.get("/history", response_model=list[HistoryEntry])
def journal(
    q: str | None = Query(None, max_length=100),
    ingredient_id: int | None = None,
    von: date | None = None,
    bis: date | None = None,
    wertung: Literal["lecker", "okay", "mies", "ohne"] | None = None,
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Alle Kochereignisse und entfallenen Essen, neueste zuerst, durchsuchbar nach Rezept und Zutat (D-JOUR)."""
    stmt = (
        select(PlanSlot, PlanWeek.start)
        .join(PlanWeek, PlanWeek.id == PlanSlot.week_id)
        .where(
            PlanSlot.date <= (min(bis, today) if bis else today),
            PlanSlot.not_cooked.is_(False),
            or_(PlanSlot.cancelled.is_(True), PlanSlot.recipe_id.is_not(None)),
        )
        .order_by(PlanSlot.date.desc(), PlanSlot.meal.asc())
    )
    if von:
        stmt = stmt.where(PlanSlot.date >= von)
    if q and q.strip():
        like = f"%{q.strip()}%"
        in_ingredients = exists().where(
            RecipeIngredient.recipe_id == PlanSlot.recipe_id,
            or_(
                RecipeIngredient.name.ilike(like),
                RecipeIngredient.ingredient_id.in_(select(Ingredient.id).where(Ingredient.name.ilike(like))),
            ),
        )
        stmt = stmt.where(PlanSlot.recipe_id.in_(select(Recipe.id).where(Recipe.title.ilike(like))) | in_ingredients)
    if ingredient_id is not None:
        stmt = stmt.where(
            exists().where(
                RecipeIngredient.recipe_id == PlanSlot.recipe_id, RecipeIngredient.ingredient_id == ingredient_id
            )
        )
    out = []
    for slot, week_start in db.execute(stmt):
        ratings = {r.person_id: r.value for r in slot.ratings}
        mittel = round(sum(ratings.values()) / len(ratings), 3) if ratings and not slot.cancelled else None
        if wertung and (slot.cancelled or not RATING_BANDS[wertung](mittel)):
            continue
        out.append(
            HistoryEntry(
                slot_id=slot.id,
                date=slot.date,
                meal=slot.meal,
                week_start=week_start,
                status="entfallen" if slot.cancelled else "gekocht",
                recipe=slot_recipe(slot.recipe),
                ratings=ratings,
                mittel=mittel,
            )
        )
        if len(out) >= MAX_HISTORY:
            break
    return out
