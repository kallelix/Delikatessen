"""Umrechnung einer Rezeptzeile in Gramm (Pflichtenheft Stufe 3, Abschnitt 4).

Reihenfolge: g und kg direkt, Volumen über die Dichte, dann das Gewicht der Einheit an der Zutat, dann die
allgemeinen Löffelmaße. Was danach übrig bleibt, ist eine Lücke und wird nicht geschätzt.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Ingredient, Recipe
from .units import UNITS

SPOON_ML = {"EL": 15.0, "TL": 5.0}
PINCH_G = {"Msp.": 0.5, "Prise": 0.5}


def to_grams(amount: float | None, unit: str | None, ingredient: Ingredient | None) -> float | None:
    """Gramm für eine Menge mit Einheit oder None, wenn das Gewicht fehlt.

    Ohne Einheit ist ein Stück gemeint („2 Eier“). Zeilen ohne Menge behandelt der Aufrufer (line_grams).
    """
    if amount is None:
        return None
    unit = unit or "Stück"
    density = (ingredient.density if ingredient else None) or 1.0
    if unit in UNITS:
        kind, factor = UNITS[unit]
        return amount * factor * (density if kind == "volumen" else 1.0)
    if ingredient is not None:
        for w in ingredient.weights:
            if w.unit == unit:
                return amount * w.grams
    if unit in SPOON_ML:
        return amount * SPOON_ML[unit] * density
    if unit in PINCH_G:
        return amount * PINCH_G[unit]
    return None


@dataclass
class LineGrams:
    grams: float | None  # None: Lücke oder ohne Menge
    gap: bool  # Menge da, aber kein Gewicht


def line_grams(amount: float | None, unit: str | None, ingredient: Ingredient | None) -> LineGrams:
    """Zeilen ohne Menge („Salz nach Geschmack“) zählen weder als Wert noch als Lücke."""
    if amount is None:
        return LineGrams(None, False)
    g = to_grams(amount, unit, ingredient)
    return LineGrams(g, g is None)


def recipe_grams(recipe: Recipe) -> list[LineGrams]:
    """Gramm je Zeile für die ganze Rezeptmenge, in der Reihenfolge der Zutaten."""
    return [line_grams(ri.amount, ri.unit, ri.ingredient) for ri in recipe.ingredients]
