"""Einkaufsliste: AK-08 mit festem Testfall."""

from tests.conftest import WEEK, ing_id, make_person

API = "/api/v1"


def recipe(client, title, servings, rows):
    body = {
        "title": title,
        "servings": servings,
        "ingredients": [{"name": n, "amount": a, "unit": u, "ingredient_id": ing_id(client, n)} for n, a, u in rows],
    }
    return client.post(f"{API}/recipes", json=body).json()


def put_recipe(client, slot_index, recipe_id):
    p = client.get(f"{API}/plans/{WEEK}").json()
    slot = p["slots"][slot_index]
    r = client.put(f"{API}/plans/{WEEK}/slots/{slot['id']}", json={"version": p["version"], "recipe_id": recipe_id})
    assert r.status_code == 200, r.text
    return r.json()


def test_ak08_fixed_case(client):
    # zwei Erwachsene und ein Kind: Faktor 1 + 1 + 0,5 = 2,5 (F-34)
    make_person(client, "Anna")
    make_person(client, "Bert")
    make_person(client, "Clara", "kind")
    a = recipe(
        client,
        "Gratin",
        4,
        [("Kartoffel", 500, "g"), ("Sahne", 200, "ml"), ("Öl", 2, "EL"), ("Zwiebel", 1, None), ("Salz", None, None)],
    )
    b = recipe(
        client,
        "Püree",
        2,
        [("Kartoffel", 1, "kg"), ("Sahne", 0.3, "l"), ("Zwiebel", 1, "Stück"), ("Öl", 2, "TL"), ("Salz", None, None)],
    )
    put_recipe(client, 1, a["id"])
    put_recipe(client, 3, b["id"])
    p = put_recipe(client, 5, a["id"])
    # dritter Platz entfällt und zählt nicht mit (Regel 5)
    client.put(f"{API}/plans/{WEEK}/slots/{p['slots'][5]['id']}", json={"version": p["version"], "cancelled": True})

    items = {(i["name"], i["unit"]): i for i in client.get(f"{API}/plans/{WEEK}/shopping").json()}
    # 500 g * 2,5/4 + 1000 g * 2,5/2 = 312,5 + 1250 = 1562,5 g -> 1,55 kg
    assert items[("Kartoffel", "kg")]["quantity"] == "1,55 kg"
    # 200 ml * 0,625 + 300 ml * 1,25 = 125 + 375 = 500 ml
    assert items[("Sahne", "ml")]["quantity"] == "500 ml"
    # EL und TL bleiben getrennte Zeilen (Regel 3)
    assert items[("Öl", "EL")]["amount"] == 1.25
    assert items[("Öl", "TL")]["amount"] == 2.5
    # Zwiebel ohne Einheit und in Stück werden zusammengefasst: 0,625 + 1,25 -> 2
    assert items[("Zwiebel", "Stück")]["amount"] == 2
    # ohne Menge genau einmal (Regel 4)
    assert items[("Salz", None)]["quantity"] == ""
    assert sum(1 for name, _ in items if name == "Salz") == 1
    assert items[("Kartoffel", "kg")]["recipes"] == ["Gratin", "Püree"]


def test_state_survives_recalculation(client):
    make_person(client)
    a = recipe(client, "Gratin", 4, [("Kartoffel", 500, "g"), ("Sahne", 200, "ml")])
    put_recipe(client, 1, a["id"])
    items = client.get(f"{API}/plans/{WEEK}/shopping").json()
    sahne = next(i for i in items if i["name"] == "Sahne")
    kart = next(i for i in items if i["name"] == "Kartoffel")
    assert client.patch(f"{API}/shopping/items/{sahne['id']}", json={"at_home": True}).json()["at_home"]
    client.patch(f"{API}/shopping/items/{kart['id']}", json={"checked": True})
    # Plan ändert sich: Menge ändert sich, Haken bleiben (Abschnitt 8)
    put_recipe(client, 3, a["id"])
    items = {i["name"]: i for i in client.get(f"{API}/plans/{WEEK}/shopping").json()}
    assert items["Sahne"]["at_home"] and items["Sahne"]["quantity"] == "100 ml"
    assert items["Kartoffel"]["checked"]
