from __future__ import annotations

import warnings
from datetime import date

import pytest

warnings.filterwarnings("ignore", message=".*httpx.*", category=DeprecationWarning)

from fastapi.testclient import TestClient  # noqa: E402

from delikatessen.config import Settings  # noqa: E402
from delikatessen.main import create_app  # noqa: E402

# Ein Mittwoch, die Planwoche beginnt am Samstag davor
TODAY = date(2026, 11, 11)
WEEK = "2026-11-07"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", allow_private_fetch=True, scheduler_enabled=False)


@pytest.fixture
def app(settings):
    app = create_app(settings)
    app.state.today_override = TODAY
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(app):
    with app.state.db.sessionmaker() as s:
        yield s


def ing_id(client, name: str) -> int:
    hits = [i for i in client.get("/api/v1/ingredients", params={"q": name}).json() if i["name"] == name]
    assert hits, name
    return hits[0]["id"]


def make_recipe(client, title: str, size: str = "haupt", ingredients=None, duration=30, servings=4, tags=()):
    ingredients = ingredients or [("Kartoffel", 500, "g")]
    body = {
        "title": title,
        "servings": servings,
        "size": size,
        "duration_min": duration,
        "steps": ["Kochen"],
        "tag_ids": list(tags),
        "ingredients": [
            {"name": n, "amount": a, "unit": u, "ingredient_id": ing_id(client, n)} for n, a, u in ingredients
        ],
    }
    r = client.post("/api/v1/recipes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def make_person_raw(client, **body):
    return client.post("/api/v1/persons", json=body)


def make_person(client, name="Anna", kind="erwachsen", nogos=(), factor=None):
    r = client.post(
        "/api/v1/persons",
        json={"name": name, "kind": kind, "portion_factor": factor, "nogos": list(nogos)},
    )
    assert r.status_code == 201, r.text
    person = r.json()
    # die App schickt das gewählte Profil in jedem Aufruf mit (N-09)
    if kind == "erwachsen" and "X-Delikatessen-Person" not in client.headers:
        client.headers["X-Delikatessen-Person"] = str(person["id"])
    return person


def plan_in_past(client, app, week_start: str, slot_index: int, recipe_id: int) -> dict:
    """Trägt ein Gericht in eine vergangene Woche ein, so wie es damals geplant wurde.

    Ganz vergangene Wochen sind nur lesbar (D-JOUR), deshalb gilt kurz das Datum jener Woche.
    """
    saved = app.state.today_override
    app.state.today_override = date.fromisoformat(week_start)
    try:
        p = client.get(f"/api/v1/plans/{week_start}").json()
        slot = p["slots"][slot_index]
        r = client.put(
            f"/api/v1/plans/{week_start}/slots/{slot['id']}", json={"version": p["version"], "recipe_id": recipe_id}
        )
        assert r.status_code == 200, r.text
        return slot
    finally:
        app.state.today_override = saved
