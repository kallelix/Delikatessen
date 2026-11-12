"""Datenmodell (Pflichtenheft Abschnitt 4)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

PERSON_KINDS = ("erwachsen", "kind")
SIZES = ("haupt", "klein")
MEALS = ("mittag", "abend")


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10), default="erwachsen")
    portion_factor: Mapped[float] = mapped_column(Float, default=1.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    netbird_ip: Mapped[str | None] = mapped_column(String(45), unique=True)

    nogos: Mapped[list[PersonNoGo]] = relationship(
        back_populates="person", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (CheckConstraint("kind in ('erwachsen','kind')", name="person_kind"),)


class IngredientGroup(Base):
    __tablename__ = "ingredient_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class Ingredient(Base):
    __tablename__ = "ingredient"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("ingredient_group.id", ondelete="SET NULL"))
    default_unit: Mapped[str | None] = mapped_column(String(20))

    group: Mapped[IngredientGroup | None] = relationship(lazy="joined")
    aliases: Mapped[list[IngredientAlias]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan", lazy="selectin"
    )


class IngredientAlias(Base):
    __tablename__ = "ingredient_alias"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredient.id", ondelete="CASCADE"))
    # immer in normalisierter Form gespeichert (siehe catalog.normalize)
    alias: Mapped[str] = mapped_column(String(80), unique=True)

    ingredient: Mapped[Ingredient] = relationship(back_populates="aliases")


class PersonNoGo(Base):
    __tablename__ = "person_nogo"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredient.id", ondelete="CASCADE"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("ingredient_group.id", ondelete="CASCADE"))

    person: Mapped[Person] = relationship(back_populates="nogos")

    __table_args__ = (
        CheckConstraint("(ingredient_id is null) <> (group_id is null)", name="nogo_ingredient_xor_group"),
    )


recipe_tag = Table(
    "recipe_tag",
    Base.metadata,
    Column("recipe_id", ForeignKey("recipe.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)


class Recipe(Base):
    __tablename__ = "recipe"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    servings: Mapped[int] = mapped_column(Integer, default=4)
    size: Mapped[str] = mapped_column(String(10), default="haupt")
    duration_min: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    image: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.position",
        lazy="selectin",
    )
    tags: Mapped[list[Tag]] = relationship(secondary=recipe_tag, lazy="selectin", order_by="Tag.name")

    __table_args__ = (
        CheckConstraint("size in ('haupt','klein')", name="recipe_size"),
        CheckConstraint("servings > 0", name="recipe_servings"),
    )

    @property
    def plannable(self) -> bool:
        """Planbar erst, wenn alle Zutaten dem Katalog zugeordnet sind (Abschnitt 4)."""
        return bool(self.ingredients) and all(ri.ingredient_id is not None for ri in self.ingredients)


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredient"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(String(200))
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredient.id", ondelete="SET NULL"))

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient | None] = relationship(lazy="joined")

    __table_args__ = (Index("ix_recipe_ingredient_recipe", "recipe_id"),)


class PlanWeek(Base):
    __tablename__ = "plan_week"

    id: Mapped[int] = mapped_column(primary_key=True)
    start: Mapped[date] = mapped_column(Date, unique=True)  # immer ein Samstag
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(12), default="entwurf")
    # Zutaten, die diese Woche verbraucht werden sollen (D-ZUT), Bonus V im Planer
    use_up: Mapped[list[int] | None] = mapped_column(JSON, default=list)

    slots: Mapped[list[PlanSlot]] = relationship(
        back_populates="week",
        cascade="all, delete-orphan",
        # mittag vor abend
        order_by="[PlanSlot.date, PlanSlot.meal.desc()]",
        lazy="selectin",
    )


class PlanSlot(Base):
    __tablename__ = "plan_slot"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("plan_week.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(10))
    size: Mapped[str] = mapped_column(String(10))
    extra: Mapped[bool] = mapped_column(Boolean, default=False)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipe.id", ondelete="SET NULL"))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    not_cooked: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(200))
    rejected: Mapped[list[int]] = mapped_column(JSON, default=list)

    week: Mapped[PlanWeek] = relationship(back_populates="slots")
    recipe: Mapped[Recipe | None] = relationship(lazy="joined")
    ratings: Mapped[list[Rating]] = relationship(back_populates="slot", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("week_id", "date", "meal", name="slot_unique_meal"),
        Index("ix_plan_slot_recipe_date", "recipe_id", "date"),
        CheckConstraint("meal in ('mittag','abend')", name="slot_meal"),
        CheckConstraint("size in ('haupt','klein')", name="slot_size"),
    )


class Rating(Base):
    __tablename__ = "rating"

    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("plan_slot.id", ondelete="CASCADE"))
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    value: Mapped[float] = mapped_column(Float)

    slot: Mapped[PlanSlot] = relationship(back_populates="ratings")

    __table_args__ = (
        UniqueConstraint("slot_id", "person_id", name="rating_unique"),
        Index("ix_rating_slot", "slot_id"),
        CheckConstraint("value in (0, 0.5, 1)", name="rating_value"),
    )


class ShoppingItem(Base):
    """Merkt sich den Zustand einer berechneten Zeile der Einkaufsliste."""

    __tablename__ = "shopping_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("plan_week.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(60))
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    at_home: Mapped[bool] = mapped_column(Boolean, default=False)
    # Zuletzt an Bring! übertragen: Kennung, Name und Mengentext (F-33). Ohne Kennung nicht in Bring!.
    bring_uuid: Mapped[str | None] = mapped_column(String(36), default=None)
    bring_name: Mapped[str | None] = mapped_column(String(200), default=None)
    bring_spec: Mapped[str | None] = mapped_column(String(200), default=None)

    __table_args__ = (UniqueConstraint("week_id", "key", name="shopping_unique_key"),)


class ImportJob(Base):
    __tablename__ = "import_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # link, spaeter text und foto
    source: Mapped[str] = mapped_column(Text)
    # wartet, laeuft, fertig, ohne_schema, fehler, uebernommen
    status: Mapped[str] = mapped_column(String(12), default="wartet")
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(300))
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipe.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class PushSubscription(Base):
    """Web-Push-Abonnement eines Geräts (F-24). Die Nachricht enthält keine Rezeptdetails."""

    __tablename__ = "push_subscription"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class Setting(Base):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict | list | int | float | str | bool | None] = mapped_column(JSON)
