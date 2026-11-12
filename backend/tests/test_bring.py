"""Bring!: AK-20 (Menge, keine Dubletten) und AK-21 (ohne Bring! bleibt die Liste nutzbar)."""

import pytest

from delikatessen.bring import MSG_OFFLINE, BringError, BringList
from tests.conftest import WEEK, ing_id, make_person

API = "/api/v1"


class FakeBring:
    """Verhält sich wie eine Bring!-Liste: Einträge über ihre Kennung, Status kaufen oder zuletzt gekauft."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.fail: str | None = None
        self.logins: list[tuple[str, str]] = []
        self.calls = 0

    def factory(self, mail, password):
        self.logins.append((mail, password))
        return self

    def lists(self):
        if self.fail:
            raise BringError(self.fail)
        return [BringList("liste-1", "Zuhause"), BringList("liste-2", "Oma")]

    def apply(self, list_uuid, changes):
        if self.fail:
            raise BringError(self.fail)
        assert list_uuid == "liste-1"
        self.calls += 1
        for c in changes:
            if c.op == "add":
                self.items[c.uuid] = {"name": c.name, "spec": c.spec, "status": "kaufen"}
            elif c.op == "complete":
                self.items[c.uuid]["status"] = "gekauft"
            else:
                self.items.pop(c.uuid, None)

    def to_buy(self):
        return sorted((i["name"], i["spec"]) for i in self.items.values() if i["status"] == "kaufen")


@pytest.fixture
def bring(app):
    fake = FakeBring()
    app.state.bring_factory = fake.factory
    app.state.settings.secret_key = "test-schluessel"
    return fake


def plan_with(client, *rows_per_recipe):
    make_person(client, "Anna")
    for i, rows in enumerate(rows_per_recipe):
        body = {
            "title": f"Gericht {i}",
            "servings": 1,
            "ingredients": [
                {"name": n, "amount": a, "unit": u, "ingredient_id": ing_id(client, n)} for n, a, u in rows
            ],
        }
        rid = client.post(f"{API}/recipes", json=body).json()["id"]
        p = client.get(f"{API}/plans/{WEEK}").json()
        r = client.put(
            f"{API}/plans/{WEEK}/slots/{p['slots'][i]['id']}", json={"version": p["version"], "recipe_id": rid}
        )
        assert r.status_code == 200, r.text


def setup_account(client):
    r = client.put(f"{API}/bring/account", json={"mail": "familie@example.org", "password": "geheim"})
    assert r.status_code == 200, r.text
    return r.json()


def shopping(client):
    return {i["name"]: i for i in client.get(f"{API}/plans/{WEEK}/shopping").json()}


def transfer(client):
    return client.post(f"{API}/plans/{WEEK}/shopping/bring")


def test_account_is_checked_and_stored_encrypted(client, bring, db):
    make_person(client, "Anna")
    lists = setup_account(client)
    assert [x["name"] for x in lists] == ["Zuhause", "Oma"]
    assert bring.logins == [("familie@example.org", "geheim")]
    cfg = client.get(f"{API}/bring").json()
    assert cfg == {
        "enabled": True,
        "configured": True,
        "mail": "familie@example.org",
        "list_uuid": "liste-1",
        "list_name": "Zuhause",
        "secret_key_missing": False,
    }
    from delikatessen.models import Setting

    stored = db.get(Setting, "bring").value
    assert "geheim" not in str(stored)
    assert client.get(f"{API}/status").json()["dienste"]["bring"] == {"aktiv": True, "hinweis": "Liste „Zuhause“"}

    # beim Übertragen wird mit dem entschlüsselten Passwort angemeldet
    client.get(f"{API}/bring/lists")
    assert bring.logins[-1] == ("familie@example.org", "geheim")


def test_wrong_password_is_not_stored(client, bring):
    make_person(client, "Anna")
    bring.fail = "Anmeldung bei Bring! fehlgeschlagen."
    r = client.put(f"{API}/bring/account", json={"mail": "familie@example.org", "password": "falsch"})
    assert r.status_code == 502 and "Anmeldung" in r.json()["detail"]
    assert client.get(f"{API}/bring").json()["configured"] is False


def test_without_secret_key_no_credentials(client, bring, app):
    make_person(client, "Anna")
    app.state.settings.secret_key = None
    r = client.put(f"{API}/bring/account", json={"mail": "familie@example.org", "password": "geheim"})
    assert r.status_code == 409 and "DELIKATESSEN_SECRET_KEY" in r.json()["detail"]


def test_ak20_amounts_and_no_duplicates(client, bring):
    plan_with(client, [("Kartoffel", 500, "g"), ("Öl", 1, "EL"), ("Salz", None, None)], [("Öl", 2, "TL")])
    setup_account(client)
    assert {i["bring"] for i in shopping(client).values()} == {"offen"}

    assert transfer(client).json() == {"uebertragen": 3, "entfernt": 0, "liste": "Zuhause"}
    # Menge als Zusatztext, gleichnamige Zeilen als ein Eintrag, ohne Menge leer
    assert bring.to_buy() == [("Kartoffel", "500 g"), ("Salz", ""), ("Öl", "1 EL + 2 TL")]
    assert {i["bring"] for i in shopping(client).values()} == {"übertragen"}

    # erneut übertragen: dieselben Kennungen, keine Dubletten
    uuids = set(bring.items)
    transfer(client)
    assert set(bring.items) == uuids and len(bring.items) == 3

    # Plan ändert sich: Eintrag wird aktualisiert statt verdoppelt
    p = client.get(f"{API}/plans/{WEEK}").json()
    kid = client.get(f"{API}/recipes", params={"q": "Gericht 0"}).json()[0]["id"]
    client.put(f"{API}/plans/{WEEK}/slots/{p['slots'][2]['id']}", json={"version": p["version"], "recipe_id": kid})
    assert shopping(client)["Kartoffel"]["bring"] == "geändert"
    transfer(client)
    assert ("Kartoffel", "1 kg") in bring.to_buy() and len(bring.items) == 3


def test_ak20_bought_at_home_and_reactivated(client, bring):
    plan_with(client, [("Kartoffel", 500, "g"), ("Sahne", 200, "ml"), ("Zwiebel", 2, "Stück")])
    setup_account(client)
    bring.items["fremd"] = {"name": "Klopapier", "spec": "", "status": "kaufen"}
    transfer(client)
    items = shopping(client)

    # in der App gekauft: in Bring! abgehakt. Schon im Haus: aus Bring! entfernt.
    client.patch(f"{API}/shopping/items/{items['Kartoffel']['id']}", json={"checked": True})
    client.patch(f"{API}/shopping/items/{items['Sahne']['id']}", json={"at_home": True})
    assert transfer(client).json()["entfernt"] == 2
    assert bring.to_buy() == [("Klopapier", ""), ("Zwiebel", "2 Stück")]
    assert [i["status"] for i in bring.items.values() if i["name"] == "Kartoffel"] == ["gekauft"]
    assert not any(i["name"] == "Sahne" for i in bring.items.values())

    # in Bring! abgehakt, aber noch gebraucht: wird wieder aktiv
    zwiebel = next(u for u, i in bring.items.items() if i["name"] == "Zwiebel")
    bring.items[zwiebel]["status"] = "gekauft"
    transfer(client)
    assert bring.items[zwiebel]["status"] == "kaufen"
    # fremde Einträge bleiben unberührt
    assert bring.items["fremd"]["status"] == "kaufen"


def test_ak21_list_usable_without_bring(client, bring):
    plan_with(client, [("Kartoffel", 500, "g")])
    # nie eingerichtet oder abgeschaltet: Übertragen geht nicht, die Liste schon
    assert transfer(client).status_code == 409
    setup_account(client)
    client.put(f"{API}/bring", json={"enabled": False})
    r = transfer(client)
    assert r.status_code == 409 and "abgeschaltet" in r.json()["detail"]
    assert client.get(f"{API}/status").json()["dienste"]["bring"]["aktiv"] is False
    item = shopping(client)["Kartoffel"]
    assert client.patch(f"{API}/shopping/items/{item['id']}", json={"checked": True}).json()["checked"] is True


def test_ak21_bring_offline_changes_nothing(client, bring):
    plan_with(client, [("Kartoffel", 500, "g")])
    setup_account(client)
    bring.fail = MSG_OFFLINE
    r = transfer(client)
    assert r.status_code == 502 and r.json()["detail"] == MSG_OFFLINE
    assert shopping(client)["Kartoffel"]["bring"] == "offen"
    # später erneut versuchen
    bring.fail = None
    assert transfer(client).status_code == 200
    assert bring.to_buy() == [("Kartoffel", "500 g")]


class StubBringApi:
    """Ersetzt bring_api.Bring, um LiveBring ohne Netz zu prüfen."""

    error: Exception | None = None
    batches: list = []

    def __init__(self, session, mail, password):
        self.mail = mail

    async def login(self):
        if StubBringApi.error:
            raise StubBringApi.error

    async def load_lists(self):
        from types import SimpleNamespace

        return SimpleNamespace(lists=[SimpleNamespace(listUuid="u1", name="Zuhause")])

    async def batch_update_list(self, list_uuid, items):
        StubBringApi.batches.append((list_uuid, items))


@pytest.fixture
def stub_bring_api(monkeypatch):
    import bring_api

    StubBringApi.error = None
    StubBringApi.batches = []
    monkeypatch.setattr(bring_api, "Bring", StubBringApi)
    return StubBringApi


def test_live_bring_request_format(stub_bring_api):
    from bring_api import BringItemOperation

    from delikatessen.bring import Change, LiveBring

    live = LiveBring("familie@example.org", "geheim")
    assert live.lists() == [BringList("u1", "Zuhause")]
    live.apply("u1", [Change("a", "Kartoffel", "500 g", "add"), Change("b", "Sahne", "", "remove")])
    assert stub_bring_api.batches == [
        (
            "u1",
            [
                {"itemId": "Kartoffel", "spec": "500 g", "uuid": "a", "operation": BringItemOperation.ADD},
                {"itemId": "Sahne", "spec": "", "uuid": "b", "operation": BringItemOperation.REMOVE},
            ],
        )
    ]
    # nichts zu tun: keine Anmeldung, kein Aufruf
    live.apply("u1", [])
    assert len(stub_bring_api.batches) == 1


@pytest.mark.parametrize(
    ("error", "message"),
    [
        ("BringAuthException", "Anmeldung bei Bring! fehlgeschlagen"),
        ("BringRequestException", "nicht erreichbar"),
        ("BringParseException", "Schnittstelle geändert"),
    ],
)
def test_live_bring_errors_become_messages(stub_bring_api, error, message):
    import bring_api

    from delikatessen.bring import LiveBring

    stub_bring_api.error = getattr(bring_api, error)("intern")
    with pytest.raises(BringError, match=message):
        LiveBring("familie@example.org", "geheim").lists()
