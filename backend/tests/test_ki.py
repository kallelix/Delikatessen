"""KI-Import (Abschnitt 7): Anfrage an das Gateway, Prüfung der Antwort, Text- und Fotoimport, Budget (AK-25)."""

import base64
import io
import json
import time

import anthropic
import httpx
import httpx2
import pytest
from PIL import Image

from delikatessen import ki
from delikatessen.config import Settings
from delikatessen.ki import KiBudgetError, KiClient, KiError, KiIngredient, KiRecipe
from tests.conftest import make_person
from tests.test_import import server  # noqa: F401  (Fixture: Testseiten über http)

API = "/api/v1"

ANSWER = {
    "found": True,
    "title": "Linsensuppe",
    "servings": 4,
    "duration_min": 45,
    "size": "klein",
    "steps": ["Zwiebel würfeln", "Linsen kochen"],
    "tags": ["vegetarisch", "Gibt es nicht"],
    "ingredients": [
        {"line": "250 g rote Linsen", "amount": 250, "unit": "g", "name": "Rote Linsen", "note": None},
        {"line": "1 Zwiebel, gewürfelt", "amount": 1, "unit": None, "name": "Zwiebel", "note": "gewürfelt"},
        {"line": "2 Essl. Olivenöl", "amount": 2, "unit": "Essl.", "name": "Olivenöl", "note": None},
        {"line": "Salz und Pfeffer", "amount": None, "unit": None, "name": "Salz", "note": None},
        {"line": "Salz und Pfeffer", "amount": None, "unit": None, "name": "Pfeffer", "note": None},
        {"line": "1 Msp. Ras el Hanout", "amount": 1, "unit": "Msp.", "name": "Ras el Hanout", "note": None},
    ],
}


def message(text: str, stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "rezept-extraktion",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1200, "output_tokens": 800},
    }


def ki_settings(tmp_path, **kw) -> Settings:
    return Settings(data_dir=tmp_path, ki_base_url="http://gateway.test", ki_api_key="sk-familie", **kw)


def client_with(settings, handler) -> tuple[KiClient, list]:
    seen: list = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(record))
    return KiClient(settings, http_client=http), seen


def jpeg_with_exif(size=(3000, 2000)) -> bytes:
    img = Image.new("RGB", size, (200, 120, 40))
    exif = Image.Exif()
    exif[0x010F] = "Telefonhersteller"
    exif[0x0110] = "Modell mit Standort"
    out = io.BytesIO()
    img.save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


# --- Anfrage an das Gateway ---------------------------------------------------------------


def test_request_to_gateway(tmp_path):
    settings = ki_settings(tmp_path)
    client, seen = client_with(settings, lambda r: httpx2.Response(200, json=message(json.dumps(ANSWER))))
    from delikatessen.images import prepare_for_ki

    photo = prepare_for_ki(jpeg_with_exif())
    recipe = client.extract(text="Rezepttext", images=[photo], tag_names=["Pasta", "vegetarisch"])
    assert recipe.title == "Linsensuppe" and len(recipe.ingredients) == 6

    (req,) = seen
    assert str(req.url) == "http://gateway.test/v1/messages"
    assert req.headers["authorization"] == "Bearer sk-familie"
    body = json.loads(req.content)
    # Alias statt Modellname, festes Schema, keine Werkzeuge (Abschnitt 11)
    assert body["model"] == "rezept-extraktion"
    assert body["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": ki.SCHEMA}}
    assert "tools" not in body and "thinking" not in body
    assert "Anweisung" in body["system"] and "nicht befolgt" in body["system"]
    image, text = body["messages"][0]["content"]
    assert image["source"]["media_type"] == "image/jpeg"
    assert "<rezept_quelle>\nRezepttext\n</rezept_quelle>" in text["text"]
    assert "Vorhandene Tags: Pasta, vegetarisch" in text["text"]
    # N-11: das Foto geht verkleinert und ohne EXIF an die KI
    sent = Image.open(io.BytesIO(base64.b64decode(image["source"]["data"])))
    assert max(sent.size) == 1568 and len(sent.getexif()) == 0


def test_schema_is_valid_for_structured_output():
    # jedes Objekt braucht additionalProperties false und alle Felder in required
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for key in ("minLength", "maxLength", "minimum", "maximum"):
                assert key not in node
            for v in node.values():
                check(v)
        elif isinstance(node, list):
            for v in node:
                check(v)

    check(ki.SCHEMA)
    assert set(ki.SCHEMA["properties"]) == set(KiRecipe.model_fields)


def test_without_structured_output_schema_goes_into_prompt(tmp_path):
    settings = ki_settings(tmp_path, ki_structured="none")
    fenced = f"```json\n{json.dumps(ANSWER)}\n```"
    client, seen = client_with(settings, lambda r: httpx2.Response(200, json=message(fenced)))
    assert client.extract(text="x").title == "Linsensuppe"
    body = json.loads(seen[0].content)
    assert body["output_config"] == {"effort": "medium"}
    assert "Antworte nur mit einem JSON-Objekt" in body["messages"][0]["content"][-1]["text"]


@pytest.mark.parametrize(
    ("status", "payload", "error", "text"),
    [
        (200, message(json.dumps(ANSWER), "refusal"), KiError, ki.MSG_REFUSAL),
        (200, message(json.dumps(ANSWER)[:50], "max_tokens"), KiError, ki.MSG_TRUNCATED),
        (200, message("Hier ist das Rezept: Linsensuppe"), KiError, ki.MSG_SCHEMA),
        (200, message(json.dumps({**ANSWER, "servings": "vier"})), KiError, ki.MSG_SCHEMA),
        (
            400,
            {"type": "error", "error": {"type": "budget_exceeded", "message": "Budget has been exceeded!"}},
            KiBudgetError,
            ki.MSG_BUDGET,
        ),
        (401, {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}, KiError, ki.MSG_KEY),
        (
            400,
            {"type": "error", "error": {"type": "invalid_request_error", "message": "unknown field"}},
            KiError,
            "Status 400",
        ),
    ],
)
def test_answers_and_errors(tmp_path, status, payload, error, text):
    client, _ = client_with(ki_settings(tmp_path), lambda r: httpx2.Response(status, json=payload))
    with pytest.raises(error) as e:
        client.extract(text="x")
    assert text in str(e.value)


def test_budget_from_gateway(tmp_path, monkeypatch):
    settings = ki_settings(tmp_path)
    answers = iter([{"info": {"spend": 1.234, "max_budget": 5}}, {"info": {"spend": 5.01, "max_budget": 5}}])

    def fake_get(url, headers, timeout):
        assert url == "http://gateway.test/key/info" and headers["Authorization"] == "Bearer sk-familie"
        return httpx.Response(200, json=next(answers))

    monkeypatch.setattr(httpx, "get", fake_get)
    ki._budget_cache.clear()
    assert ki.status(settings) == {"aktiv": True, "hinweis": "1,23 von 5,00 USD diesen Monat"}
    ki._budget_cache.clear()
    assert ki.status(settings) == {"aktiv": False, "hinweis": "Budget aufgebraucht (5,01 von 5,00 USD)"}
    assert ki.status(Settings(data_dir=tmp_path)) == {"aktiv": False, "hinweis": "nicht eingerichtet"}


# --- Importe über die Schnittstelle --------------------------------------------------------


class FakeKi:
    def __init__(self, answer=ANSWER, error: Exception | None = None):
        self.answer, self.error, self.calls = answer, error, []

    def factory(self, settings):
        return self

    def extract(self, *, text=None, images=(), tag_names=()):
        self.calls.append({"text": text, "images": list(images), "tags": list(tag_names)})
        if self.error:
            raise self.error
        return KiRecipe.model_validate(self.answer)


@pytest.fixture
def fake_ki(app, monkeypatch):
    fake = FakeKi()
    app.state.settings.ki_base_url = "http://gateway.test"
    app.state.settings.ki_api_key = "sk-familie"
    app.state.imports.ki_factory = fake.factory
    monkeypatch.setattr(ki, "budget", lambda settings, ttl_s=300: None)
    return fake


def wait(client, job, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"{API}/imports/{job['id']}").json()
        if job["status"] not in ("wartet", "laeuft"):
            return job
        time.sleep(0.05)
    raise AssertionError("Import hängt")


def test_ak23_text_import_ends_in_preview(client, fake_ki):
    r = client.post(f"{API}/imports", json={"kind": "text", "text": "Linsensuppe für vier: 250 g rote Linsen …"})
    assert r.status_code == 202, r.text
    job = wait(client, r.json())
    assert job["status"] == "fertig", job
    res = job["result"]
    assert (res["title"], res["servings"], res["size"], res["ki"]) == ("Linsensuppe", 4, "klein", True)
    # nur vorhandene Tags, Unbekanntes fällt weg
    tags = {t["name"]: t["id"] for t in client.get(f"{API}/tags").json()}
    assert res["tag_ids"] == [tags["vegetarisch"]]
    rows = {i["name"]: i for i in res["ingredients"]}
    # Zuordnung zum Katalog wie beim Link-Import, Einheiten vereinheitlicht
    assert rows["Zwiebel"]["ingredient_name"] == "Zwiebel" and rows["Zwiebel"]["note"] == "gewürfelt"
    assert rows["Olivenöl"]["unit"] == "EL"
    assert rows["Salz"]["ingredient_name"] == "Salz" and rows["Pfeffer"]["ingredient_name"] == "Pfeffer"
    assert rows["Ras el Hanout"]["ingredient_id"] is None  # unbekannt, wird in der Vorschau zugeordnet
    assert fake_ki.calls[0]["text"].startswith("Linsensuppe für vier")
    assert "vegetarisch" in fake_ki.calls[0]["tags"]


def test_photo_import_strips_exif_and_deletes_photos(client, fake_ki, app):
    files = [("bilder", (f"seite{i}.jpg", jpeg_with_exif(), "image/jpeg")) for i in range(2)]
    r = client.post(f"{API}/imports/foto", files=files)
    assert r.status_code == 202, r.text
    job = wait(client, r.json())
    assert job["status"] == "fertig" and job["source"] == "2 Fotos"
    sent = fake_ki.calls[0]["images"]
    assert len(sent) == 2
    for raw in sent:
        img = Image.open(io.BytesIO(raw))
        assert max(img.size) <= 1568 and len(img.getexif()) == 0
    # Fotos liegen nur bis zur Auswertung auf dem Server
    assert not (app.state.settings.data_dir / "import" / str(job["id"])).exists()


def test_photo_import_limits(client, fake_ki):
    too_many = [("bilder", (f"{i}.jpg", jpeg_with_exif((50, 50)), "image/jpeg")) for i in range(5)]
    assert client.post(f"{API}/imports/foto", files=too_many).status_code == 422
    bad = [("bilder", ("x.jpg", b"kein Bild", "image/jpeg"))]
    r = client.post(f"{API}/imports/foto", files=bad)
    assert r.status_code == 422 and "kein lesbares Bild" in r.json()["detail"]


def test_no_recipe_found(client, fake_ki):
    fake_ki.answer = {**ANSWER, "found": False, "ingredients": []}
    job = wait(client, client.post(f"{API}/imports", json={"kind": "text", "text": "Einkaufszettel"}).json())
    assert job["status"] == "fehler" and "kein Rezept" in job["error"]


def test_link_without_schema_goes_to_ki(client, fake_ki, server):  # noqa: F811
    url = f"{server}/ohne_schema.html"
    job = wait(client, client.post(f"{API}/imports", json={"kind": "link", "url": url}).json())
    assert job["status"] == "fertig" and job["result"]["source_url"] == url
    assert "<script" not in fake_ki.calls[0]["text"]

    # KI scheitert: wie in Stufe 1 das Formular mit Titel und Quelle, dazu der Grund
    fake_ki.error = KiError("Das KI-Gateway ist gerade nicht erreichbar.")
    job = wait(client, client.post(f"{API}/imports", json={"kind": "link", "url": url}).json())
    assert job["status"] == "ohne_schema" and "nicht erreichbar" in job["error"]
    assert job["result"]["source_url"] == url


def test_without_ki_text_and_photos_are_refused(client):
    r = client.post(f"{API}/imports", json={"kind": "text", "text": "Linsensuppe"})
    assert r.status_code == 409 and "nicht eingerichtet" in r.json()["detail"]
    r = client.post(f"{API}/imports/foto", files=[("bilder", ("a.jpg", jpeg_with_exif((50, 50)), "image/jpeg"))])
    assert r.status_code == 409
    assert client.get(f"{API}/status").json()["dienste"]["ki"] == {"aktiv": False, "hinweis": "nicht eingerichtet"}


def test_ak25_budget_exhausted(client, fake_ki, monkeypatch):
    monkeypatch.setattr(ki, "budget", lambda settings, ttl_s=300: ki.Budget(spend=5.2, max_budget=5))
    r = client.post(f"{API}/imports", json={"kind": "text", "text": "Linsensuppe"})
    assert r.status_code == 409 and r.json()["detail"] == ki.MSG_BUDGET
    assert client.get(f"{API}/status").json()["dienste"]["ki"]["aktiv"] is False
    # alles ohne KI läuft weiter
    make_person(client, "Anna")
    assert client.get(f"{API}/plans/aktuell").status_code == 200
    assert client.get(f"{API}/recipes").status_code == 200

    # Budget läuft während des Imports aus: die Vorschau zeigt den Hinweis
    monkeypatch.setattr(ki, "budget", lambda settings, ttl_s=300: None)
    fake_ki.error = KiBudgetError(ki.MSG_BUDGET)
    job = wait(client, client.post(f"{API}/imports", json={"kind": "text", "text": "Linsensuppe"}).json())
    assert job["status"] == "fehler" and job["error"] == ki.MSG_BUDGET


def test_ki_ingredient_model_is_lenient_about_missing_values():
    i = KiIngredient(line="Salz", amount=None, unit=None, name="Salz", note=None)
    assert i.amount is None
