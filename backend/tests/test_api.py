"""Schnittstellentests: Rezepte, Suche, Bilder, Familie, Profile, Bewertungen, Einstellungen, Export."""

import io
from datetime import date, timedelta

from PIL import Image

from tests.conftest import TODAY, WEEK, ing_id, make_person, make_recipe, plan_in_past

API = "/api/v1"


def test_recipe_crud_and_scaling_fields(client):
    r = make_recipe(client, "Kartoffelgratin", ingredients=[("Kartoffel", 1.2, "kg"), ("Sahne", 400, "ml")])
    assert r["plannable"] and r["servings"] == 4
    assert r["ingredients"][0]["ingredient_name"] == "Kartoffel"
    body = {
        "title": "Kartoffelgratin klassisch",
        "servings": 6,
        "size": "haupt",
        "steps": ["Schälen", "", "Backen"],
        "ingredients": [
            {"name": "Kartoffeln", "amount": 1.5, "unit": "Kilogramm", "ingredient_id": ing_id(client, "Kartoffel")}
        ],
    }
    r2 = client.put(f"{API}/recipes/{r['id']}", json=body).json()
    assert r2["title"] == "Kartoffelgratin klassisch" and r2["steps"] == ["Schälen", "Backen"]
    assert r2["ingredients"][0]["unit"] == "kg"
    assert client.delete(f"{API}/recipes/{r['id']}").status_code == 204
    assert client.get(f"{API}/recipes/{r['id']}").status_code == 404


def test_required_fields(client):
    assert client.post(f"{API}/recipes", json={"title": "Leer", "ingredients": []}).status_code == 422
    assert client.post(f"{API}/recipes", json={"title": "", "ingredients": [{"name": "x"}]}).status_code == 422


def test_search_and_filters(client):
    veg = client.get(f"{API}/tags").json()
    veg_id = next(t["id"] for t in veg if t["name"] == "vegetarisch")
    make_recipe(
        client, "Käsespätzle", ingredients=[("Spätzle", 500, "g"), ("Emmentaler", 200, "g")], duration=40, tags=[veg_id]
    )
    make_recipe(
        client, "Spaghetti Bolognese", ingredients=[("Spaghetti", 500, "g"), ("Hackfleisch", 400, "g")], duration=60
    )
    make_recipe(client, "Obstsalat", "klein", ingredients=[("Apfel", 2, "Stück")], duration=10)

    def titles(**params):
        return [r["title"] for r in client.get(f"{API}/recipes", params=params).json()]

    assert titles(q="spätz") == ["Käsespätzle"]
    assert titles(q="kase") == ["Käsespätzle"]  # Umlaute vereinfacht
    assert titles(q="hackfleisch") == ["Spaghetti Bolognese"]  # Suche über Zutaten
    assert titles(tag=veg_id) == ["Käsespätzle"]
    assert titles(size="klein") == ["Obstsalat"]
    assert titles(max_duration=45) == ["Käsespätzle", "Obstsalat"]
    assert titles(q="nichtda") == []


def test_favorite_and_exclude_toggle(client):
    r = make_recipe(client, "Lasagne")
    assert client.patch(f"{API}/recipes/{r['id']}", json={"favorite": True}).json()["favorite"]
    assert client.get(f"{API}/recipes", params={"favorite": True}).json()[0]["id"] == r["id"]
    assert client.patch(f"{API}/recipes/{r['id']}", json={"excluded": True}).json()["excluded"]
    assert not client.patch(f"{API}/recipes/{r['id']}", json={"excluded": False}).json()["excluded"]


def test_image_upload_resizes_and_strips_exif(client, settings):
    r = make_recipe(client, "Foto")
    img = Image.new("RGB", (4000, 3000), "orange")
    exif = Image.Exif()
    exif[0x010F] = "Kamerahersteller"
    exif[0x8825] = {2: (52.0, 31.0, 0.0)}  # GPS
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    resp = client.post(f"{API}/recipes/{r['id']}/image", files={"file": ("a.jpg", buf.getvalue(), "image/jpeg")})
    assert resp.status_code == 200, resp.text
    url = resp.json()["image_url"]
    data = client.get(url).content
    with Image.open(io.BytesIO(data)) as out:
        assert out.format == "WEBP" and max(out.size) == 1600
        assert not out.getexif()
    bad = client.post(f"{API}/recipes/{r['id']}/image", files={"file": ("a.jpg", b"kein bild", "image/jpeg")})
    assert bad.status_code == 422
    assert client.get(f"{API}/images/../delikatessen.sqlite3").status_code == 404


def test_persons_profile_and_adult_guard(client, settings):
    anna = make_person(client, "Anna")
    kind = make_person(client, "Ida", "kind")
    assert kind["portion_factor"] == 0.5 and anna["portion_factor"] == 1.0
    assert client.get(f"{API}/me").json()["name"] == "Anna"
    # Kinderprofil darf keine Einstellungen ändern (Bedienschutz, N-09)
    s = client.get(f"{API}/settings").json()
    r = client.put(f"{API}/settings", json=s, headers={"X-Delikatessen-Person": str(kind["id"])})
    assert r.status_code == 403
    assert client.put(f"{API}/settings", json=s).status_code == 200


def test_profile_by_netbird_ip(client):
    anna = make_person(client, "Anna")
    client.put(f"{API}/persons/{anna['id']}", json={**anna, "netbird_ip": "100.64.0.7", "nogos": []})
    del client.headers["X-Delikatessen-Person"]
    # TestClient kommt von "testclient", keine Zuordnung
    assert client.get(f"{API}/me").json() is None
    # Weitergeleitete Adresse zählt nur vom vertrauten Proxy
    from fastapi.testclient import TestClient

    app = client.app
    app.state.settings.trusted_proxies = "10.0.0.9"
    with TestClient(app, client=("10.0.0.5", 1234)) as other:
        assert other.get(f"{API}/me", headers={"X-Forwarded-For": "100.64.0.7"}).json() is None
    app.state.settings.trusted_proxies = "10.0.0.5"
    with TestClient(app, client=("10.0.0.5", 1234)) as proxy:
        assert proxy.get(f"{API}/me", headers={"X-Forwarded-For": "100.64.0.7"}).json()["name"] == "Anna"
    with TestClient(app, client=("100.64.0.7", 1234)) as direct:
        assert direct.get(f"{API}/me").json()["name"] == "Anna"


def test_nogo_validation(client):
    make_person(client)
    r = client.post(f"{API}/persons", json={"name": "X", "nogos": [{"ingredient_id": 1, "group_id": 1}]})
    assert r.status_code == 422


def test_ratings_rankings_and_history(client):
    anna = make_person(client, "Anna")
    ida = make_person(client, "Ida", "kind")
    lieb = make_recipe(client, "Lieblingsessen")
    make_recipe(client, "Anderes")
    p = client.get(f"{API}/plans/{WEEK}").json()
    past = [s for s in p["slots"] if date.fromisoformat(s["date"]) <= TODAY]
    future = [s for s in p["slots"] if date.fromisoformat(s["date"]) > TODAY]
    v = p["version"]
    for s in past[:3]:
        v = client.put(f"{API}/plans/{WEEK}/slots/{s['id']}", json={"version": v, "recipe_id": lieb["id"]}).json()[
            "version"
        ]
    v = client.put(f"{API}/plans/{WEEK}/slots/{future[0]['id']}", json={"version": v, "recipe_id": lieb["id"]}).json()[
        "version"
    ]

    # offene Bewertungen nur für Vergangenes
    open_ = client.get(f"{API}/ratings/open").json()
    assert len(open_) == 3 and set(open_[0]["missing_person_ids"]) == {anna["id"], ida["id"]}
    # Zukunft kann nicht bewertet werden
    assert client.put(f"{API}/slots/{future[0]['id']}/ratings/{anna['id']}", json={"value": 1}).status_code == 422
    for s in past[:3]:
        client.put(f"{API}/slots/{s['id']}/ratings/{anna['id']}", json={"value": 1})
        # Eltern werten stellvertretend fürs Kind
        client.put(f"{API}/slots/{s['id']}/ratings/{ida['id']}", json={"value": 0.5})
    assert client.get(f"{API}/ratings/open").json() == []
    # Wertung ist änderbar und löschbar
    r = client.put(f"{API}/slots/{past[0]['id']}/ratings/{ida['id']}", json={"value": 1}).json()
    assert r == {str(anna["id"]): 1.0, str(ida["id"]): 1.0}
    assert client.put(f"{API}/slots/{past[0]['id']}/ratings/{ida['id']}", json={"value": 0.7}).status_code == 422

    ranking = client.get(f"{API}/rankings").json()["ranking"]
    assert ranking[0]["recipe"]["title"] == "Lieblingsessen"
    # (1+1+1+1+0,5+0,5 + 2*0,5) / 8 = 0,75
    assert ranking[0]["favorite_score"] == 0.75 and ranking[0]["cooked_count"] == 3

    detail = client.get(f"{API}/recipes/{lieb['id']}").json()
    assert detail["cooked_count"] == 3 and detail["last_cooked"] == max(s["date"] for s in past[:3])

    # "nicht gekocht" nimmt den Platz aus der Historie (F-11)
    v = client.get(f"{API}/plans/{WEEK}").json()["version"]
    client.put(f"{API}/plans/{WEEK}/slots/{past[0]['id']}", json={"version": v, "not_cooked": True})
    assert client.get(f"{API}/recipes/{lieb['id']}").json()["cooked_count"] == 2


def test_long_not_eaten(client, app):
    make_person(client)
    r = make_recipe(client, "Gulasch")
    old_week = (date.fromisoformat(WEEK) - timedelta(days=84)).isoformat()
    slot = plan_in_past(client, app, old_week, 1, r["id"])
    me = client.get(f"{API}/me").json()
    client.put(f"{API}/slots/{slot['id']}/ratings/{me['id']}", json={"value": 1})
    lang = client.get(f"{API}/rankings").json()["long_not_eaten"]
    assert [e["recipe"]["title"] for e in lang] == ["Gulasch"]


def test_candidates_respect_hard_rules(client):
    pilz = ing_id(client, "Champignons")
    make_person(client, nogos=[{"ingredient_id": pilz}])
    make_recipe(client, "Pilze", ingredients=[("Champignons", 200, "g")])
    make_recipe(client, "Salat", "klein", ingredients=[("Kopfsalat", 1, "Kopf")])
    make_recipe(client, "Braten", ingredients=[("Schweinebraten", 1, "kg")])
    p = client.get(f"{API}/plans/{WEEK}").json()
    main = next(s for s in p["slots"] if s["size"] == "haupt")
    titles = [r["title"] for r in client.get(f"{API}/plans/{WEEK}/slots/{main['id']}/candidates").json()]
    assert titles == ["Braten", "Salat"]


def test_settings_validation(client):
    s = client.get(f"{API}/settings").json()
    assert s["weights"] == {"F": 0.5, "L": 0.25, "T": 0.1, "A": 0.15, "V": 0.3, "N": 0.1}
    s["grid"]["0"] = ["frühstück"]
    assert client.put(f"{API}/settings", json=s).status_code == 422
    s["grid"]["0"] = ["mittag", "abend"]
    s["plan_time"] = "19:30"
    out = client.put(f"{API}/settings", json=s).json()
    assert out["grid"]["0"] == ["mittag", "abend"] and out["plan_time"] == "19:30"
    # neue Wochen nutzen das neue Raster
    p = client.get(f"{API}/plans/2026-11-14").json()
    monday = [x for x in p["slots"] if x["date"] == "2026-11-16"]
    assert [(x["meal"], x["size"]) for x in monday] == [("mittag", "klein"), ("abend", "haupt")]


def test_export_schema_org(client):
    make_recipe(client, "Gratin", ingredients=[("Kartoffel", 1.2, "kg")], duration=50)
    r = client.get(f"{API}/export/recipes")
    assert r.headers["content-disposition"].startswith("attachment")
    data = r.json()
    assert data[0]["@type"] == "Recipe" and data[0]["totalTime"] == "PT50M"
    assert data[0]["recipeIngredient"] == ["1,2 kg Kartoffel"]


def test_status_and_openapi(client):
    assert client.get(f"{API}/status").json()["datenbank"] == "ok"
    assert "/api/v1/recipes" in client.get(f"{API}/openapi.json").json()["paths"]
