"""Ein- und Ausgabeformate der Schnittstelle."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from ..units import normalize_unit

Size = Literal["haupt", "klein"]
Meal = Literal["mittag", "abend"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Katalog ---------------------------------------------------------------------------


class GroupOut(Out):
    id: int
    name: str


class IngredientOut(Out):
    id: int
    name: str
    group_id: int | None
    group: str | None = None
    default_unit: str | None
    aliases: list[str] = []


class IngredientIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    group_id: int | None = None
    default_unit: str | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return " ".join(v.split())


class TagOut(Out):
    id: int
    name: str


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


# --- Rezepte ---------------------------------------------------------------------------


class RecipeIngredientIn(BaseModel):
    amount: float | None = Field(None, ge=0)
    unit: str | None = Field(None, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    note: str | None = Field(None, max_length=200)
    ingredient_id: int | None = None

    @field_validator("unit")
    @classmethod
    def _unit(cls, v: str | None) -> str | None:
        return normalize_unit(v) if v and v.strip() else None


class RecipeIngredientOut(RecipeIngredientIn):
    ingredient_name: str | None = None


class RecipeIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    servings: int = Field(4, ge=1, le=100)
    size: Size = "haupt"
    duration_min: int | None = Field(None, ge=1, le=24 * 60)
    steps: list[str] = []
    tag_ids: list[int] = []
    ingredients: list[RecipeIngredientIn] = Field(min_length=1)
    source_url: str | None = Field(None, max_length=1000)
    favorite: bool = False
    excluded: bool = False

    @field_validator("steps")
    @classmethod
    def _steps(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s.strip()]


class RecipePatch(BaseModel):
    favorite: bool | None = None
    excluded: bool | None = None


class RecipeSummary(BaseModel):
    id: int
    title: str
    size: Size
    duration_min: int | None
    image_url: str | None
    favorite: bool
    excluded: bool
    plannable: bool
    tags: list[TagOut]


class RecipeOut(RecipeSummary):
    servings: int
    steps: list[str]
    ingredients: list[RecipeIngredientOut]
    source_url: str | None
    favorite_score: float
    cooked_count: int
    last_cooked: date | None
    cooked_dates: list[date]


# --- Familie ---------------------------------------------------------------------------


class NoGo(BaseModel):
    ingredient_id: int | None = None
    group_id: int | None = None


class NoGoOut(NoGo):
    name: str


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["erwachsen", "kind"] = "erwachsen"
    portion_factor: float | None = Field(None, gt=0, le=5)
    active: bool = True
    netbird_ip: str | None = None
    nogos: list[NoGo] = []

    @field_validator("netbird_ip")
    @classmethod
    def _ip(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        import ipaddress

        return str(ipaddress.ip_address(v.strip()))


class PersonOut(BaseModel):
    id: int
    name: str
    kind: str
    portion_factor: float
    active: bool
    netbird_ip: str | None
    nogos: list[NoGoOut]


# --- Plan ------------------------------------------------------------------------------


class SlotRecipe(BaseModel):
    id: int
    title: str
    image_url: str | None
    duration_min: int | None
    size: Size


class SlotOut(BaseModel):
    id: int
    date: date
    meal: Meal
    size: Size
    extra: bool
    recipe: SlotRecipe | None
    pinned: bool
    cancelled: bool
    not_cooked: bool
    reason: str | None
    cooked: bool
    rateable: bool
    ratings: dict[int, float]


class UseUpItem(BaseModel):
    id: int
    name: str


class PlanOut(BaseModel):
    start: date
    end: date
    version: int
    status: str
    # ganz vergangene Woche: nur lesbar, Wertungen nachtragbar (D-JOUR)
    readonly: bool = False
    # diese Woche verbrauchen (D-ZUT)
    use_up: list[UseUpItem] = []
    slots: list[SlotOut]


class Versioned(BaseModel):
    version: int


class SlotAdd(Versioned):
    first: date
    last: date | None = None
    meal: Meal
    size: Size = "klein"


class SlotUpdate(Versioned):
    recipe_id: int | None = None
    clear_recipe: bool = False
    pinned: bool | None = None
    cancelled: bool | None = None
    not_cooked: bool | None = None
    swap_main: bool = False


class UseUpIn(Versioned):
    ingredient_ids: list[int] = Field(default_factory=list, max_length=30)


class GenerateIn(BaseModel):
    version: int | None = None
    seed: int | None = None


class RatingIn(BaseModel):
    """0 = mies, 0,5 = okay, 1 = lecker, None löscht die Wertung (F-10)."""

    value: float | None

    @field_validator("value")
    @classmethod
    def _value(cls, v: float | None) -> float | None:
        if v is not None and v not in (0, 0.5, 1):
            raise ValueError("Wertung muss 0, 0.5 oder 1 sein")
        return v


class OpenRating(BaseModel):
    slot_id: int
    date: date
    meal: Meal
    recipe: SlotRecipe
    missing_person_ids: list[int]


class RankingEntry(BaseModel):
    recipe: RecipeSummary
    favorite_score: float
    ratings: int
    cooked_count: int
    last_cooked: date | None


class MonthDish(BaseModel):
    recipe: RecipeSummary
    monat: str  # JJJJ-MM
    mittel: float
    wertungen: int
    laufend: bool  # True: aktueller Monat, kann sich noch ändern


class NewDish(BaseModel):
    recipe: RecipeSummary
    erstmals: date


class Badge(BaseModel):
    name: str
    beschreibung: str
    ziel: int
    stand: int
    erreicht: bool


class Rankings(BaseModel):
    ranking: list[RankingEntry]
    long_not_eaten: list[RankingEntry]
    # D-RANK: Essen des Monats ab zwei Wertungen, neu ausprobierte Gerichte, Abzeichen der Familie
    essen_des_monats: MonthDish | None = None
    neu_ausprobiert: list[NewDish] = []
    abzeichen: list[Badge] = []


# --- Einkauf ---------------------------------------------------------------------------


class ShoppingItemOut(BaseModel):
    id: int
    name: str
    group: str
    amount: float | None
    unit: str | None
    quantity: str
    recipes: list[str]
    checked: bool
    at_home: bool
    # Stand in Bring!: offen, übertragen, geändert oder None (nicht gebraucht und nicht in Bring!)
    bring: str | None = None


class ShoppingPatch(BaseModel):
    checked: bool | None = None
    at_home: bool | None = None


# --- Import ----------------------------------------------------------------------------


class ImportIn(BaseModel):
    kind: Literal["link", "text"] = "link"
    url: HttpUrl | None = None
    # eingefügter oder diktierter Rezepttext (D-SPR)
    text: str | None = Field(None, max_length=20_000)

    @model_validator(mode="after")
    def _source(self):
        if self.kind == "link" and self.url is None:
            raise ValueError("Für einen Link-Import fehlt die Adresse")
        if self.kind == "text" and not (self.text and self.text.strip()):
            raise ValueError("Der Text ist leer")
        return self


class ImportOut(BaseModel):
    id: int
    kind: str
    source: str
    status: str
    result: dict | None
    error: str | None
    recipe_id: int | None


class ImportAccept(BaseModel):
    recipe: RecipeIn
    image_url: str | None = None
