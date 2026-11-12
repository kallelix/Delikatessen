"""Stufe 2, M7: Verbrauchen und Neues im Planer, Zutatensuche, Rangliste, Journal (AK-27), Push und
Donnerstagslauf (AK-26)."""

from datetime import date, timedelta

import pytest

from delikatessen.scheduler import next_week_start, thursday_run
from tests.conftest import TODAY, WEEK, ing_id, make_person, make_recipe, plan_in_past

API = "/api/v1"
NEXT = (date.fromisoformat(WEEK) + timedelta(days=7)).isoformat()


def plan(client, start=WEEK):
    return client.get(f"{API}/plans/{start}").json()


# --- Planer: verbrauchen (V) und neues probieren (N) ---------------------------------------


def test_use_up_bonus_once_and_named_reason(client):
    make_person(client)
    zucchini = ing_id(client, "Zucchini")
    make_recipe(client, "Zucchinipfanne", ingredients=[("Zucchini", 2, "Stück"), ("Reis", 200, "g")])
    for title in ("Gulasch", "Lasagne", "Curry", "Pizza", "Risotto"):
        make_recipe(client, title)
    make_recipe(client, "Salat", "klein", ingredients=[("Paprika", 1, "Stück")])

    p = plan(client)
    r = client.put(f"{API}/plans/{WEEK}/use-up", json={"version": p["version"], "ingredient_ids": [zucchini, 999999]})
    assert r.status_code == 200, r.text
    assert r.json()["use_up"] == [{"id": zucchini, "name": "Zucchini"}]  # Unbekanntes fällt weg

    for seed in range(5):
        p = client.post(f"{API}/plans/{WEEK}/generate", json={"seed": seed}).json()
        reasons = [s["reason"] for s in p["slots"] if s["recipe"]]
        # die Pfanne kommt mit Grund in den Plan, der Bonus gilt aber nur einmal
        assert reasons.count("verbraucht Zucchini") == 1, (seed, reasons)
        assert any(s["recipe"]["title"] == "Zucchinipfanne" for s in p["slots"] if s["recipe"])


def test_new_dish_bonus():
    from delikatessen import history, planner
    from delikatessen.appsettings import AppSettings

    class R:
        id, favorite, duration_min, ingredients = 1, False, 30, []

    cand = planner.Candidate(R(), set(), set(), set())
    slot = type("Slot", (), {"date": TODAY})()
    stats_new = {}
    stats_old = {1: history.RecipeStats(cooked=[TODAY - timedelta(days=5)])}
    ctx = planner.Context(AppSettings(), TODAY, stats_new, [], [cand], set())
    fresh = planner.score(cand, slot, [], ctx)
    ctx.stats = stats_old
    known = planner.score(cand, slot, [], ctx)
    # N (0,1) und L (0,5 bei nie gekocht) machen den Unterschied
    assert fresh.score > known.score


# --- Zutatensuche (D-ZUT) ------------------------------------------------------------------


def test_search_by_ingredients(client):
    make_person(client)
    make_recipe(client, "Zucchini mit Feta", ingredients=[("Zucchini", 2, "Stück"), ("Feta", 200, "g")])
    make_recipe(
        client, "Gemüsereis", ingredients=[("Zucchini", 1, "Stück"), ("Reis", 200, "g"), ("Paprika", 1, "Stück")]
    )
    make_recipe(client, "Nudeln pur", ingredients=[("Nudeln", 500, "g")])
    ids = [ing_id(client, "Zucchini"), ing_id(client, "Feta")]
    hits = client.get(f"{API}/search/by-ingredients", params={"ids": ids}).json()
    assert [(h["recipe"]["title"], h["anteil"], h["fehlend"]) for h in hits] == [
        ("Zucchini mit Feta", 1.0, 0),
        ("Gemüsereis", 0.333, 2),
    ]
    assert hits[0]["treffer"] == ["Feta", "Zucchini"]
    assert client.get(f"{API}/search/by-ingredients").json() == []


# --- Journal und vergangene Wochen (D-JOUR, AK-27) -----------------------------------------


@pytest.fixture
def history_data(client, app):
    anna = make_person(client, "Anna")
    gulasch = make_recipe(client, "Gulasch", ingredients=[("Hackfleisch", 500, "g")])
    curry = make_recipe(client, "Curry", ingredients=[("Reis", 200, "g")])
    weeks = [(date.fromisoformat(WEEK) - timedelta(days=7 * k)).isoformat() for k in (6, 3, 1)]
    slots = [plan_in_past(client, app, w, 1, gulasch["id"]) for w in weeks]
    curry_slot = plan_in_past(client, app, weeks[2], 3, curry["id"])
    client.put(f"{API}/slots/{slots[0]['id']}/ratings/{anna['id']}", json={"value": 1})
    client.put(f"{API}/slots/{curry_slot['id']}/ratings/{anna['id']}", json={"value": 0})
    # ein entfallenes Essen in der Vorwoche
    saved = app.state.today_override
    app.state.today_override = date.fromisoformat(weeks[2])
    p = plan(client, weeks[2])
    client.put(f"{API}/plans/{weeks[2]}/slots/{p['slots'][5]['id']}", json={"version": p["version"], "cancelled": True})
    app.state.today_override = saved
    return {"anna": anna, "gulasch": gulasch, "slots": slots, "weeks": weeks, "curry_slot": curry_slot}


def test_ak27_journal_finds_all_dates(client, history_data):
    entries = client.get(f"{API}/history", params={"q": "gulasch"}).json()
    assert [e["date"] for e in entries] == sorted((s["date"] for s in history_data["slots"]), reverse=True)
    assert {e["status"] for e in entries} == {"gekocht"}
    # Suche nach Zutat, Name und Katalog
    assert len(client.get(f"{API}/history", params={"q": "hackfleisch"}).json()) == 3
    hack = ing_id(client, "Hackfleisch")
    assert len(client.get(f"{API}/history", params={"ingredient_id": hack}).json()) == 3
    # Wertung und Zeitraum
    lecker = client.get(f"{API}/history", params={"wertung": "lecker"}).json()
    assert [e["recipe"]["title"] for e in lecker] == ["Gulasch"] and lecker[0]["mittel"] == 1
    assert [e["recipe"]["title"] for e in client.get(f"{API}/history", params={"wertung": "mies"}).json()] == ["Curry"]
    recent = client.get(f"{API}/history", params={"von": history_data["weeks"][2]}).json()
    assert {e["status"] for e in recent} == {"gekocht", "entfallen"}
    assert len([e for e in recent if e["status"] == "gekocht"]) == 2
    # Rezeptseite: zuletzt gekocht und alle Termine
    detail = client.get(f"{API}/recipes/{history_data['gulasch']['id']}").json()
    assert detail["cooked_dates"] == [e["date"] for e in entries]


def test_ak27_past_week_readonly_but_rateable(client, history_data):
    week = history_data["weeks"][1]
    p = plan(client, week)
    assert p["readonly"] is True and plan(client)["readonly"] is False
    v = p["version"]
    assert client.post(f"{API}/plans/{week}/generate", json={"version": v}).status_code == 409
    slot = history_data["slots"][1]
    r = client.put(f"{API}/plans/{week}/slots/{slot['id']}", json={"version": v, "pinned": False})
    assert r.status_code == 409 and "nur lesbar" in r.json()["detail"]
    # Wertung nachtragen geht
    r = client.put(f"{API}/slots/{slot['id']}/ratings/{history_data['anna']['id']}", json={"value": 0.5})
    assert r.status_code == 200
    # "nicht gekocht" bleibt markierbar (F-11)
    r = client.put(f"{API}/plans/{week}/slots/{slot['id']}", json={"version": v, "not_cooked": True})
    assert r.status_code == 200


# --- Rangliste (D-RANK) ---------------------------------------------------------------------


def test_dish_of_month_new_dishes_and_badges(client, app):
    anna = make_person(client, "Anna")
    ben = make_person(client, "Ben", "kind")
    a = make_recipe(client, "Gulasch")
    b = make_recipe(client, "Curry")
    # beide im November gekocht, Gulasch mit zwei Wertungen
    s1 = plan_in_past(client, app, WEEK, 0, a["id"])
    s2 = plan_in_past(client, app, WEEK, 1, b["id"])
    for person, value in ((anna, 1), (ben, 0.5)):
        client.put(f"{API}/slots/{s1['id']}/ratings/{person['id']}", json={"value": value})
    client.put(f"{API}/slots/{s2['id']}/ratings/{anna['id']}", json={"value": 1})  # nur eine Wertung

    r = client.get(f"{API}/rankings").json()
    dish = r["essen_des_monats"]
    assert dish["recipe"]["title"] == "Gulasch" and dish["monat"] == "2026-11"
    assert (dish["wertungen"], dish["mittel"], dish["laufend"]) == (2, 0.75, True)
    assert {n["recipe"]["title"] for n in r["neu_ausprobiert"]} == {"Gulasch", "Curry"}
    badges = {b["name"]: b for b in r["abzeichen"]}
    assert badges["Erster Versuch"]["erreicht"] and not badges["Neugierig"]["erreicht"]
    assert badges["Neugierig"]["stand"] == 2 and badges["Neugierig"]["ziel"] == 5


def test_no_dish_of_month_with_single_ratings(client, app):
    anna = make_person(client, "Anna")
    a = make_recipe(client, "Gulasch")
    s = plan_in_past(client, app, WEEK, 0, a["id"])
    client.put(f"{API}/slots/{s['id']}/ratings/{anna['id']}", json={"value": 1})
    assert client.get(f"{API}/rankings").json()["essen_des_monats"] is None


# --- Push und Donnerstagslauf (F-24, AK-26) ----------------------------------------------


class FakePush:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.gone: set[str] = set()

    def factory(self, settings):
        return self.send

    def send(self, subscription, data):
        from pywebpush import WebPushException

        if subscription["endpoint"] in self.gone:
            raise WebPushException("weg", response=type("R", (), {"status_code": 410, "text": ""})())
        self.sent.append((subscription["endpoint"], data))


@pytest.fixture
def fake_push(app):
    fake = FakePush()
    app.state.push_sender_factory = fake.factory
    return fake


def subscribe(client, n):
    endpoint = f"https://push.example.org/geraet-{n}"
    r = client.post(
        f"{API}/push/subscriptions", json={"endpoint": endpoint, "keys": {"p256dh": "B" * 87, "auth": "a" * 22}}
    )
    assert r.status_code == 201, r.text
    return endpoint


def test_push_key_and_subscriptions(client, fake_push, app):
    key = client.get(f"{API}/push/key").json()["public_key"]
    assert len(key) == 87 and client.get(f"{API}/push/key").json()["public_key"] == key
    assert (app.state.settings.data_dir / "vapid_private.pem").exists()

    make_person(client)
    e1 = subscribe(client, 1)
    subscribe(client, 1)  # erneut: kein zweites Abonnement
    assert client.get(f"{API}/status").json()["dienste"]["push"] == {"aktiv": True, "hinweis": "1 Gerät"}
    r = client.post(f"{API}/push/test", json={"endpoint": e1}).json()
    assert r == {"gesendet": 1, "entfernt": 0, "fehler": 0}
    assert "Benachrichtigung" in fake_push.sent[0][1]
    client.request("DELETE", f"{API}/push/subscriptions", json={"endpoint": e1})
    assert client.get(f"{API}/status").json()["dienste"]["push"]["aktiv"] is False
    # nur https-Endpunkte der Push-Dienste
    bad = {"endpoint": "http://intern/x", "keys": {"p256dh": "B" * 87, "auth": "a" * 22}}
    assert client.post(f"{API}/push/subscriptions", json=bad).status_code == 422


def test_ak26_thursday_run_creates_draft_and_notifies(client, app, fake_push):
    make_person(client)
    for title in ("Gulasch", "Lasagne", "Curry"):
        make_recipe(client, title)
    make_recipe(client, "Salat", "klein", ingredients=[("Paprika", 1, "Stück")])
    e1, e2 = subscribe(client, 1), subscribe(client, 2)
    fake_push.gone.add(e2)  # Gerät hat die Benachrichtigungen abbestellt

    thursday = TODAY + timedelta(days=1)
    assert next_week_start(thursday).isoformat() == NEXT
    result = thursday_run(app.state.db.sessionmaker, thursday, fake_push.send)
    assert result["erzeugt"] is True and result["woche"] == NEXT
    assert (result["gesendet"], result["entfernt"]) == (1, 1)
    p = plan(client, NEXT)
    assert all(s["recipe"] for s in p["slots"])
    endpoint, data = fake_push.sent[0]
    assert endpoint == e1 and "14.11." in data
    # keine Rezeptdetails in der Nachricht
    assert not any(t in data for t in ("Gulasch", "Lasagne", "Curry", "Salat"))

    # besteht schon ein Plan, bleibt er unverändert und es geht keine Nachricht raus
    again = thursday_run(app.state.db.sessionmaker, thursday, fake_push.send)
    assert again["erzeugt"] is False and plan(client, NEXT)["version"] == p["version"]
    assert len(fake_push.sent) == 1


def test_run_now_endpoint_and_reschedule(client, app, fake_push):
    from delikatessen.scheduler import Scheduler

    make_person(client)
    make_recipe(client, "Gulasch")
    assert client.post(f"{API}/push/donnerstagslauf").json()["erzeugt"] is True

    sched = Scheduler(app.state.db.sessionmaker, app.state.settings, fake_push.factory)
    app.state.scheduler = sched
    sched.start()
    try:
        job = sched._sched.get_job(Scheduler.JOB)
        assert (job.next_run_time.weekday(), job.next_run_time.hour, job.next_run_time.minute) == (3, 18, 0)
        s = client.get(f"{API}/settings").json()
        s["plan_time"] = "19:30"
        client.put(f"{API}/settings", json=s)
        job = sched._sched.get_job(Scheduler.JOB)
        assert (job.next_run_time.weekday(), job.next_run_time.hour, job.next_run_time.minute) == (3, 19, 30)
    finally:
        sched.shutdown()
