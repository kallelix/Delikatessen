"""Planer: Abnahmekriterien AK-01 bis AK-05, AK-13 und AK-14."""

import random
import time
from datetime import date, timedelta

from delikatessen import appsettings, planner
from delikatessen.history import RecipeStats, favorite_score, long_not_eaten
from delikatessen.models import PlanWeek
from tests.conftest import TODAY, WEEK, ing_id, make_person, make_recipe

API = "/api/v1"


def plan(client):
    return client.get(f"{API}/plans/{WEEK}").json()


def generate(client, seed=1):
    p = plan(client)
    r = client.post(f"{API}/plans/{WEEK}/generate", json={"version": p["version"], "seed": seed})
    assert r.status_code == 200, r.text
    return r.json()


def test_standard_grid():
    # 9 Plätze: Sa und So je zwei, Mo bis Fr abends (F-25), am Wochenende je eine Hauptmahlzeit (F-26)
    slots = planner.standard_slots(date(2026, 11, 7), appsettings.AppSettings())
    assert len(slots) == 9
    assert sum(s.size == "haupt" for s in slots) == 7
    assert [(s.date.weekday(), s.meal, s.size) for s in slots[:4]] == [
        (5, "mittag", "klein"),
        (5, "abend", "haupt"),
        (6, "mittag", "klein"),
        (6, "abend", "haupt"),
    ]


def test_week_start():
    assert planner.week_start(date(2026, 11, 7)) == date(2026, 11, 7)
    assert planner.week_start(date(2026, 11, 13)) == date(2026, 11, 7)
    assert planner.week_start(date(2026, 11, 14)) == date(2026, 11, 14)


def test_scores():
    assert favorite_score(None, False) == 0.5
    assert favorite_score(RecipeStats(ratings=[1, 1]), False) == 0.75
    assert favorite_score(RecipeStats(ratings=[1, 1, 1, 1, 1, 1]), True) == 1.0
    assert long_not_eaten(None, TODAY) == 0.5
    assert long_not_eaten(RecipeStats(cooked=[TODAY - timedelta(days=30)]), TODAY) == 0.5
    assert long_not_eaten(RecipeStats(cooked=[TODAY - timedelta(days=90)]), TODAY) == 1.0


def test_ak01_200_recipes_under_3_seconds(client):
    kid = ing_id(client, "Kartoffel")
    for i in range(200):
        body = {
            "title": f"Gericht {i}",
            "size": "haupt" if i % 4 else "klein",
            "duration_min": 20 + i % 50,
            "ingredients": [{"name": "Kartoffel", "amount": 100, "unit": "g", "ingredient_id": kid}],
        }
        assert client.post(f"{API}/recipes", json=body).status_code == 201
    p = plan(client)
    t0 = time.perf_counter()
    r = client.post(f"{API}/plans/{WEEK}/generate", json={"version": p["version"]})
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 3
    assert all(s["recipe"] for s in r.json()["slots"])


def test_ak02_no_nogo_in_1000_plans(client, app, db):
    nuss = ing_id(client, "Walnuss")
    pilz = ing_id(client, "Champignons")
    groups = {g["name"]: g["id"] for g in client.get(f"{API}/ingredient-groups").json()}
    make_person(client, "Anna", nogos=[{"ingredient_id": pilz}])
    make_person(client, "Ben", "kind", nogos=[{"group_id": groups["Fisch und Meeresfrüchte"]}])
    make_person(client, "Oma", nogos=[{"ingredient_id": nuss}])
    # Oma ist nicht aktiv: ihr No-go zählt nicht
    oma = next(p for p in client.get(f"{API}/persons").json() if p["name"] == "Oma")
    client.put(f"{API}/persons/{oma['id']}", json={**oma, "active": False, "nogos": [{"ingredient_id": nuss}]})

    bad = {
        make_recipe(client, "Pilzpfanne", ingredients=[("Champignons", 300, "g")])["id"],
        make_recipe(client, "Lachs", ingredients=[("Lachs", 300, "g")])["id"],
        make_recipe(client, "Garnelen klein", "klein", ingredients=[("Garnelen", 100, "g")])["id"],
    }
    make_recipe(client, "Walnussnudeln", ingredients=[("Walnuss", 50, "g"), ("Nudeln", 400, "g")])
    for i in range(6):
        make_recipe(client, f"Haupt {i}")
        make_recipe(client, f"Klein {i}", "klein")

    plan(client)
    week = db.query(PlanWeek).one()
    settings = appsettings.load(db)
    seen = set()
    for seed in range(1000):
        planner.generate(db, week, settings, TODAY, random.Random(seed))
        ids = {s.recipe_id for s in week.slots}
        assert not ids & bad
        seen |= ids
    assert any(r["title"] == "Walnussnudeln" and r["id"] in seen for r in client.get(f"{API}/recipes").json())


def test_ak03_regenerate_keeps_pinned_and_cancelled(client):
    for i in range(8):
        make_recipe(client, f"Haupt {i}")
        make_recipe(client, f"Klein {i}", "klein")
    p = generate(client)
    pinned, cancelled = p["slots"][1], p["slots"][4]
    p = client.put(f"{API}/plans/{WEEK}/slots/{pinned['id']}", json={"version": p["version"], "pinned": True}).json()
    p = client.put(
        f"{API}/plans/{WEEK}/slots/{cancelled['id']}", json={"version": p["version"], "cancelled": True}
    ).json()
    cancelled_recipe = next(s for s in p["slots"] if s["id"] == cancelled["id"])["recipe"]
    for seed in range(20):
        p = generate(client, seed)
        by_id = {s["id"]: s for s in p["slots"]}
        assert by_id[pinned["id"]]["recipe"]["id"] == pinned["recipe"]["id"]
        assert by_id[cancelled["id"]]["cancelled"]
        assert by_id[cancelled["id"]]["recipe"] == cancelled_recipe


def test_ak04_few_recipes_repeat_and_empty_reason(client):
    for i in range(5):
        make_recipe(client, f"Haupt {i}")
    p = generate(client)
    mains = [s for s in p["slots"] if s["size"] == "haupt"]
    assert all(s["recipe"] for s in mains)
    assert len({s["recipe"]["id"] for s in mains}) < len(mains)  # Wiederholungen sind gewollt
    small = [s for s in p["slots"] if s["size"] == "klein"]
    assert small and all(s["recipe"] is None and "kleine Mahlzeit" in s["reason"] for s in small)


def test_ak05_weekend_one_main_per_day(client):
    for weekend_main in ("abend", "mittag"):
        s = client.get(f"{API}/settings").json()
        s["weekend_main"] = weekend_main
        client.put(f"{API}/settings", json=s)
        start = date(2026, 11, 14) if weekend_main == "abend" else date(2026, 11, 21)
        p = client.get(f"{API}/plans/{start}").json()
        for day in (start, start + timedelta(days=1)):
            sizes = [x["size"] for x in p["slots"] if x["date"] == day.isoformat()]
            assert sizes.count("haupt") == 1
        main = next(x for x in p["slots"] if x["size"] == "haupt" and x["date"] == start.isoformat())
        assert main["meal"] == weekend_main


def test_swap_main_on_weekend(client):
    p = plan(client)
    sat_lunch = p["slots"][0]
    p = client.put(
        f"{API}/plans/{WEEK}/slots/{sat_lunch['id']}", json={"version": p["version"], "swap_main": True}
    ).json()
    assert [s["size"] for s in p["slots"][:2]] == ["haupt", "klein"]


def test_ak13_extra_lunch_slots_and_cancelled_not_in_shopping(client):
    make_person(client)
    for i in range(3):
        make_recipe(client, f"Haupt {i}")
    for i in range(3):
        make_recipe(client, f"Klein {i}", "klein", ingredients=[("Ei", 2, "Stück")])
    p = plan(client)
    p = client.post(
        f"{API}/plans/{WEEK}/slots",
        json={"version": p["version"], "first": "2026-11-09", "last": "2026-11-13", "meal": "mittag"},
    ).json()
    extras = [s for s in p["slots"] if s["extra"]]
    assert len(extras) == 5 and all(s["size"] == "klein" for s in extras)
    p = generate(client)
    assert all(s["recipe"] for s in p["slots"])

    # ein entfallener Platz erscheint nicht in der Einkaufsliste
    p = client.put(
        f"{API}/plans/{WEEK}/slots/{extras[0]['id']}", json={"version": p["version"], "cancelled": True}
    ).json()
    eggs = sum(2 for s in p["slots"] if s["size"] == "klein" and not s["cancelled"])
    items = client.get(f"{API}/plans/{WEEK}/shopping").json()
    egg = next(i for i in items if i["name"] == "Ei")
    assert egg["amount"] == eggs / 4  # eine Person mit Faktor 1, Rezepte für 4

    # Zusatzplätze lassen sich wieder entfernen, Standardplätze nicht
    r = client.delete(f"{API}/plans/{WEEK}/slots/{extras[1]['id']}", params={"version": p["version"]})
    assert r.status_code == 200
    std = next(s for s in r.json()["slots"] if not s["extra"])
    assert (
        client.delete(f"{API}/plans/{WEEK}/slots/{std['id']}", params={"version": r.json()["version"]}).status_code
        == 422
    )


def test_ak14_new_suggestion_never_repeats(client):
    for i in range(10):
        make_recipe(client, f"Haupt {i}")
    p = generate(client)
    slot = next(s for s in p["slots"] if s["size"] == "haupt")
    seen = {slot["recipe"]["id"]}
    for seed in range(5):
        p = client.post(
            f"{API}/plans/{WEEK}/slots/{slot['id']}/suggest", json={"version": p["version"], "seed": seed}
        ).json()
        rid = next(s for s in p["slots"] if s["id"] == slot["id"])["recipe"]["id"]
        assert rid not in seen
        seen.add(rid)


def test_version_conflict(client):
    p = plan(client)
    assert client.post(f"{API}/plans/{WEEK}/generate", json={"version": p["version"]}).status_code == 200
    r = client.post(f"{API}/plans/{WEEK}/generate", json={"version": p["version"]})
    assert r.status_code == 409


def test_time_limit_prefers_quick_dishes(client):
    make_recipe(client, "Schnell", duration=20)
    make_recipe(client, "Langsam", duration=120)
    counts = {"Schnell": 0, "Langsam": 0}
    for seed in range(50):
        p = generate(client, seed)
        for s in p["slots"]:
            if s["size"] == "haupt" and date.fromisoformat(s["date"]).weekday() < 5:
                counts[s["recipe"]["title"]] += 1
    assert counts["Schnell"] > counts["Langsam"]


def test_hard_filters_unplannable_and_excluded(client):
    kid = ing_id(client, "Kartoffel")
    open_recipe = client.post(
        f"{API}/recipes",
        json={
            "title": "Offen",
            "ingredients": [{"name": "Kartoffel", "ingredient_id": kid}, {"name": "Zauberpulver"}],
        },
    ).json()
    assert not open_recipe["plannable"]
    excluded = make_recipe(client, "Ausgeschlossen")
    client.patch(f"{API}/recipes/{excluded['id']}", json={"excluded": True})
    p = generate(client)
    assert all(s["recipe"] is None for s in p["slots"])
    assert any("No-go" not in (s["reason"] or "") for s in p["slots"])
