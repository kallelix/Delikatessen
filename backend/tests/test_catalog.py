from delikatessen.catalog import Matcher


def name_of(db, ingredient_id):
    from delikatessen.models import Ingredient

    return db.get(Ingredient, ingredient_id).name if ingredient_id else None


def test_matching_order(db):
    m = Matcher(db)
    assert name_of(db, m.match("Kartoffel")) == "Kartoffel"  # exakter Name
    assert name_of(db, m.match("Möhren")) == "Karotte"  # Alias
    assert name_of(db, m.match("TOMATEN")) == "Tomate"  # Kleinschreibung, Einzahl
    assert name_of(db, m.match("Eier")) == "Ei"
    assert name_of(db, m.match("Zwiebeln")) == "Zwiebel"
    assert name_of(db, m.match("Reis")) == "Reis"
    assert m.match("frische Drachenfrucht") is None  # Unbekanntes bleibt offen


def test_alias_is_learned(client, db):
    from tests.conftest import ing_id

    kid = ing_id(client, "Kartoffel")
    body = {
        "title": "Ofenkartoffel",
        "ingredients": [{"name": "Drillinge", "amount": 1, "unit": "kg", "ingredient_id": kid}],
    }
    assert client.post("/api/v1/recipes", json=body).status_code == 201
    assert name_of(db, Matcher(db).match("Drillinge")) == "Kartoffel"


def test_seed_is_idempotent(db):
    from sqlalchemy import func, select

    from delikatessen.catalog import seed
    from delikatessen.models import Ingredient

    before = db.scalar(select(func.count()).select_from(Ingredient))
    seed(db)
    assert db.scalar(select(func.count()).select_from(Ingredient)) == before
    assert before > 100
