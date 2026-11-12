"""In der App einstellbare Werte (F-41), gespeichert in der Tabelle setting."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .models import MEALS, Setting

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


class Weights(BaseModel):
    F: float = Field(0.50, ge=0, le=5)
    L: float = Field(0.25, ge=0, le=5)
    T: float = Field(0.10, ge=0, le=5)
    A: float = Field(0.15, ge=0, le=5)
    # Stufe 2: Bonus für "diese Woche verbrauchen" (D-ZUT) und für noch nie gekochte Gerichte
    V: float = Field(0.30, ge=0, le=5)
    N: float = Field(0.10, ge=0, le=5)


class AppSettings(BaseModel):
    # Standardraster: je Wochentag (0 = Montag) die geplanten Mahlzeiten (F-25)
    grid: dict[int, list[str]] = Field(
        default_factory=lambda: {
            0: ["abend"],
            1: ["abend"],
            2: ["abend"],
            3: ["abend"],
            4: ["abend"],
            5: ["mittag", "abend"],
            6: ["mittag", "abend"],
        }
    )
    # Welche Wochenendmahlzeit die große ist (F-26)
    weekend_main: str = "abend"
    # Zeitlimit für den Aufwand je Wochentag in Minuten, None = kein Limit
    time_limits: dict[int, int | None] = Field(
        default_factory=lambda: {0: 45, 1: 45, 2: 45, 3: 45, 4: 45, 5: None, 6: None}
    )
    weights: Weights = Field(default_factory=Weights)
    # Uhrzeit des automatischen Planvorschlags am Donnerstag (F-24)
    plan_time: str = Field("18:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @field_validator("grid")
    @classmethod
    def _check_grid(cls, v: dict[int, list[str]]) -> dict[int, list[str]]:
        out = {}
        for day in range(7):
            meals = v.get(day, [])
            for m in meals:
                if m not in MEALS:
                    raise ValueError(f"Unbekannte Mahlzeit {m}")
            out[day] = [m for m in MEALS if m in meals]
        return out

    @field_validator("time_limits")
    @classmethod
    def _check_limits(cls, v: dict[int, int | None]) -> dict[int, int | None]:
        return {day: v.get(day) for day in range(7)}

    @field_validator("weekend_main")
    @classmethod
    def _check_main(cls, v: str) -> str:
        if v not in MEALS:
            raise ValueError("weekend_main muss mittag oder abend sein")
        return v


KEY = "app"


def load(session: Session) -> AppSettings:
    row = session.get(Setting, KEY)
    if row is None or not isinstance(row.value, dict):
        return AppSettings()
    return AppSettings.model_validate(row.value)


def save(session: Session, settings: AppSettings) -> AppSettings:
    row = session.get(Setting, KEY)
    data = settings.model_dump(mode="json")
    if row is None:
        session.add(Setting(key=KEY, value=data))
    else:
        row.value = data
    session.commit()
    return settings
