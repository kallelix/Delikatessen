"""Kochhistorie und Favoritenwert (F-11, F-12, Abschnitt 6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PlanSlot, Rating

PRIOR_COUNT = 2
PRIOR_VALUE = 0.5
STAR_BONUS = 0.2
LONG_DAYS = 60


@dataclass
class RecipeStats:
    ratings: list[float] = field(default_factory=list)
    cooked: list[date] = field(default_factory=list)

    @property
    def last_cooked(self) -> date | None:
        return max(self.cooked) if self.cooked else None


def is_cooked(slot: PlanSlot, today: date) -> bool:
    """Ein vergangener Platz gilt als gekocht, solange er nicht als nicht gekocht markiert ist."""
    return slot.recipe_id is not None and not slot.cancelled and not slot.not_cooked and slot.date <= today


def collect(session: Session, today: date) -> dict[int, RecipeStats]:
    stats: dict[int, RecipeStats] = {}
    rows = session.execute(
        select(PlanSlot.id, PlanSlot.recipe_id, PlanSlot.date).where(
            PlanSlot.recipe_id.is_not(None),
            PlanSlot.cancelled.is_(False),
            PlanSlot.not_cooked.is_(False),
            PlanSlot.date <= today,
        )
    ).all()
    slot_recipe = {}
    for slot_id, recipe_id, d in rows:
        stats.setdefault(recipe_id, RecipeStats()).cooked.append(d)
        slot_recipe[slot_id] = recipe_id
    if slot_recipe:
        for slot_id, value in session.execute(
            select(Rating.slot_id, Rating.value).where(Rating.slot_id.in_(slot_recipe))
        ):
            stats[slot_recipe[slot_id]].ratings.append(value)
    return stats


def favorite_score(st: RecipeStats | None, starred: bool) -> float:
    """F: Mittel der Wertungen, mit zwei angenommenen Wertungen von 0,5 geglättet, Stern +0,2, höchstens 1."""
    ratings = st.ratings if st else []
    f = (sum(ratings) + PRIOR_COUNT * PRIOR_VALUE) / (len(ratings) + PRIOR_COUNT)
    if starred:
        f += STAR_BONUS
    return min(f, 1.0)


def long_not_eaten(st: RecipeStats | None, ref: date) -> float:
    """L: Tage seit dem letzten Kochen geteilt durch 60, höchstens 1. Noch nie gekocht: 0,5."""
    if st is None or not st.cooked:
        return 0.5
    before = [d for d in st.cooked if d <= ref]
    if not before:
        return 0.5
    return min((ref - max(before)).days / LONG_DAYS, 1.0)
