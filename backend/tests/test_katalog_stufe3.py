"""Stufe 3, M8: Katalog mit Gruppen, Gewichten, Dichte und Saison (Pflichtenheft Stufe 3, Abschnitt 4)."""

from dataclasses import replace

import pytest
from sqlalchemy import select

from delikatessen import catalog
from delikatessen.catalog import (
    FOOD_GROUPS,
    SEASON_CATEGORIES,
    CatalogError,
    load_catalog,
    parse_catalog,
    parse_season,
    seed,
)
from delikatessen.grams import line_grams, to_grams
from delikatessen.models import Ingredient
from delikatessen.units import UNITS
from tests.conftest import ing_id, make_person, make_recipe

API = "/api/v1"


def ing(db, name) -> Ingredient:
    return db.scalar(select(Ingredient).where(Ingredient.name == name))


# --- katalog.yml ------------------------------------------------------------------------------


def test_ak30_catalog_complete():
    cat = load_catalog()
    assert len(cat.entries) >= 146
    for e in cat.entries.values():
        assert e.food_group in FOOD_GROUPS, e.name
        if e.unit not in UNITS:
            assert e.unit in e.weights, f"{e.name}: Gewicht für {e.unit} fehlt"
        if e.category in SEASON_CATEGORIES:
            assert e.season_given, f"{e.name}: Saison oder Grund für ganzjährig fehlt"


def test_catalog_groups_from_category_with_exceptions():
    e = load_catalog().entries
    assert e["Zwiebel"].food_group == "Gemüse"
    assert e["Kartoffel"].food_group == "Kartoffeln"
    assert e["Petersilie"].food_group == "Sonstiges"
    assert e["Parmesan"].food_group == "Milch"
    assert e["Speck"].food_group == "Wurst"
    assert e["Passierte Tomaten"].food_group == "Gemüse"
    assert e["Spargel"].season_months == [4, 5, 6]
    assert e["Kartoffel"].season_months is None and e["Kartoffel"].season_given


def test_parse_season():
    assert parse_season("4-6") == [4, 5, 6]
    assert parse_season("1-3, 7-12") == [1, 2, 3, 7, 8, 9, 10, 11, 12]
    assert parse_season("10-2") == [1, 2, 10, 11, 12]  # über den Jahreswechsel
    assert parse_season("5") == [5]
    assert parse_season(5) == [5]
    assert parse_season("ganzjährig (Lagerware)") is None
    for bad in ("", "13", "Mai", "4-6-8", "0-3"):
        with pytest.raises(CatalogError):
            parse_season(bad)


@pytest.mark.parametrize(
    "item, message",
    [
        ("{einheit: Schüssel}", "Einheit"),
        ("{einheit: g, gruppe: Gemuese}", "Gruppe"),
        ("{einheit: g, gewicht: {g: 5}}", "Zähl-Einheiten"),
        ("{einheit: Stück, gewicht: {Stück: 0}}", "positive Zahl"),
        ("{einheit: g, farbe: rot}", "unbekannte Felder"),
    ],
)
def test_parse_catalog_rejects_mistakes(item, message):
    text = f"kategorien:\n  Gemüse:\n    gruppe: Gemüse\n    zutaten:\n      Testrübe: {item}\n"
    with pytest.raises(CatalogError, match=message):
        parse_catalog(text)


# --- Abgleich beim Start ----------------------------------------------------------------------


def test_seed_fills_new_fields(db):
    z = ing(db, "Zwiebel")
    assert z.food_group == "Gemüse"
    assert {w.unit: w.grams for w in z.weights} == {"Stück": 80}
    assert ing(db, "Öl").density == 0.92
    assert ing(db, "Spargel").season_months == [4, 5, 6]
    assert ing(db, "Kartoffel").season_months is None


def test_seed_upgrades_existing_database(db):
    """Datenbank aus Stufe 2: Zutaten ohne neue Felder bekommen sie beim ersten Start mit 0004."""
    z = ing(db, "Zwiebel")
    z.catalog_applied = None
    z.food_group = None
    z.weights.clear()
    db.commit()
    seed(db)
    z = ing(db, "Zwiebel")
    assert z.food_group == "Gemüse" and {w.unit: w.grams for w in z.weights} == {"Stück": 80}


def with_entry(monkeypatch, name, **changes):
    cat = load_catalog()
    entries = dict(cat.entries)
    entries[name] = replace(entries[name], **changes)
    monkeypatch.setattr(catalog, "load_catalog", lambda: replace(cat, entries=entries))


def test_family_changes_survive_until_catalog_changes_same_value(client, db, monkeypatch):
    zid = ing_id(client, "Zwiebel")
    body = client.get(f"{API}/ingredients/{zid}").json()
    body.update(weights={"Stück": 100, "Kopf": 300}, food_group="Sonstiges")
    assert client.put(f"{API}/ingredients/{zid}", json=body).status_code == 200

    # Katalog unverändert: nichts wird überschrieben
    seed(db)
    db.expire_all()
    z = ing(db, "Zwiebel")
    assert z.food_group == "Sonstiges" and {w.unit: w.grams for w in z.weights} == {"Stück": 100, "Kopf": 300}

    # Katalog ändert nur die Dichte: die kommt an, Gewicht und Gruppe der Familie bleiben
    with_entry(monkeypatch, "Zwiebel", density=0.9)
    seed(db)
    db.expire_all()
    z = ing(db, "Zwiebel")
    assert z.density == 0.9 and z.food_group == "Sonstiges" and z.weights[1].grams == 100

    # Katalog korrigiert das Stückgewicht: die Korrektur gewinnt
    with_entry(monkeypatch, "Zwiebel", density=0.9, weights={"Stück": 90})
    seed(db)
    db.expire_all()
    assert {w.unit: w.grams for w in ing(db, "Zwiebel").weights} == {"Stück": 90, "Kopf": 300}


def test_catalog_removes_weight_unless_family_changed_it(db, monkeypatch):
    with_entry(monkeypatch, "Sellerie", weights={"Stange": 50})
    seed(db)
    db.expire_all()
    assert {w.unit for w in ing(db, "Sellerie").weights} == {"Stange"}


def test_new_alias_from_catalog_and_deleted_alias_stays_deleted(client, db, monkeypatch):
    lid = ing_id(client, "Lauch")
    body = client.get(f"{API}/ingredients/{lid}").json()
    body["aliases"] = []  # Familie streicht „porree“
    assert client.put(f"{API}/ingredients/{lid}", json=body).status_code == 200
    with_entry(monkeypatch, "Lauch", aliases=("Porree", "Winterlauch"))
    seed(db)
    db.expire_all()
    assert sorted(a.alias for a in ing(db, "Lauch").aliases) == ["winterlauch"]


# --- Umrechnung in Gramm ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "amount, unit, name, grams",
    [
        (200, "g", "Mehl", 200),
        (1.5, "kg", "Kartoffel", 1500),
        (100, "ml", "Öl", 92),  # Dichte
        (0.5, "l", "Milch", 500),
        (2, "Stück", "Zwiebel", 160),  # Gewicht der Einheit
        (2, None, "Ei", 100),  # ohne Einheit ist ein Stück gemeint
        (2, "EL", "Olivenöl", 28),  # Gewicht geht vor Löffelmaß
        (1, "EL", "Butter", 12),
        (1, "EL", "Sahne", 15),  # Löffelmaß mal Dichte 1,0
        (1, "TL", "Salz", 6),  # 5 ml mal 1,2
        (1, "EL", "Mehl", 10),
        (1, "Prise", "Pfeffer", 0.2),
        (1, "Msp.", "Zimt", 0.5),  # Rückfallwert
        (1, "Dose", "Mais", None),  # Lücke
        (1, "Bund", "Spinat", None),
    ],
)
def test_to_grams(db, amount, unit, name, grams):
    g = to_grams(amount, unit, ing(db, name))
    assert g == pytest.approx(grams) if grams is not None else g is None


def test_line_without_amount_is_no_gap(db):
    salt = ing(db, "Salz")
    assert line_grams(None, None, salt).gap is False
    assert line_grams(1, "Dose", ing(db, "Mais")).gap is True
    assert line_grams(1, "Stück", None).gap is True  # ohne Katalog kein Gewicht


# --- Zutaten pflegen --------------------------------------------------------------------------


def test_put_ingredient_only_for_adults(client):
    make_person(client, "Anna")
    kid = make_person(client, "Ida", kind="kind")
    zid = ing_id(client, "Zwiebel")
    body = client.get(f"{API}/ingredients/{zid}").json()
    r = client.put(f"{API}/ingredients/{zid}", json=body, headers={"X-Delikatessen-Person": str(kid["id"])})
    assert r.status_code == 403
    assert client.put(f"{API}/ingredients/{zid}", json=body).status_code == 200


def test_put_ingredient_validates(client):
    zid = ing_id(client, "Zwiebel")
    body = client.get(f"{API}/ingredients/{zid}").json()
    put = lambda **kw: client.put(f"{API}/ingredients/{zid}", json={**body, **kw})  # noqa: E731
    assert put(food_group="Gemuese").status_code == 422
    assert put(season_months=[0]).status_code == 422
    assert put(weights={"g": 5}).status_code == 422
    assert put(weights={"Stück": -1}).status_code == 422
    assert put(aliases=["Möhre"]).status_code == 409  # gehört schon zur Karotte
    assert put(aliases=["Lauch"]).status_code == 409  # eigene Zutat
    r = put(aliases=["Zwiebeln", "Speisezwiebel"], weights={"stk": 70}, season_months=[9, 8, 8])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["aliases"] == ["speisezwiebel", "zwiebeln"]
    assert out["weights"] == {"Stück": 70}
    assert out["season_months"] == [8, 9]


def test_gaps_sorted_by_recipes(client):
    make_recipe(client, "Maissalat", ingredients=[("Mais", 1, "Dose"), ("Zwiebel", 1, "Stück")])
    make_recipe(client, "Maissuppe", ingredients=[("Mais", 2, "Dose"), ("Spinat", 1, "Bund")])
    new = client.post(f"{API}/ingredients", json={"name": "Drachenfrucht"}).json()
    assert new["food_group"] is None
    gaps = client.get(f"{API}/ingredients/gaps").json()
    by_name = {g["ingredient"]["name"]: g for g in gaps}
    assert gaps[0]["ingredient"]["name"] == "Mais"
    assert by_name["Mais"] == {**by_name["Mais"], "recipes": 2, "missing_units": ["Dose"], "missing_group": False}
    assert by_name["Drachenfrucht"]["missing_group"] is True and by_name["Drachenfrucht"]["recipes"] == 0
    assert "Zwiebel" not in by_name

    mid = by_name["Mais"]["ingredient"]["id"]
    body = client.get(f"{API}/ingredients/{mid}").json()
    body["weights"] = {"Dose": 285}
    client.put(f"{API}/ingredients/{mid}", json=body)
    assert "Mais" not in {g["ingredient"]["name"] for g in client.get(f"{API}/ingredients/gaps").json()}


def test_new_ingredient_gets_group_of_category(client):
    groups = {g["name"]: g["id"] for g in client.get(f"{API}/ingredient-groups").json()}
    r = client.post(f"{API}/ingredients", json={"name": "Romanesco", "group_id": groups["Gemüse"]})
    assert r.json()["food_group"] == "Gemüse"
