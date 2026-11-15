"""Update-Hinweis und Knopf: die App liest nur Dateien des Hosts und legt eine Anforderung an."""

import json
from datetime import datetime, timedelta

import pytest

from delikatessen import __version__
from delikatessen.update import parse_version
from tests.conftest import make_person

API = "/api/v1"


@pytest.fixture
def update_dir(app, tmp_path):
    d = tmp_path / "update"
    d.mkdir()
    app.state.settings.update_dir = d
    return d


def newer() -> str:
    major, minor, patch = parse_version(__version__)
    return f"v{major}.{minor}.{patch + 1}"


def write(d, name, data):
    (d / name).write_text(json.dumps(data), "utf-8")


def test_without_update_dir_there_is_nothing(client):
    assert client.get(f"{API}/status").json()["update"] is None
    assert client.post(f"{API}/update").status_code == 409


def test_hint_when_newer_release(client, update_dir):
    write(
        update_dir,
        "neueste.json",
        {"neueste": newer(), "url": "https://example.org/r", "geprueft": "2026-11-15T03:00:00+01:00"},
    )
    u = client.get(f"{API}/status").json()["update"]
    assert (u["verfuegbar"], u["neueste"], u["knopf"], u["laeuft"]) == (True, newer(), True, False)
    # gleiche oder ältere Version: kein Hinweis, auch bei Unsinn in der Datei
    for value in (f"v{__version__}", "v0.0.1", "kaputt", None):
        write(update_dir, "neueste.json", {"neueste": value})
        assert client.get(f"{API}/status").json()["update"]["verfuegbar"] is False
    (update_dir / "neueste.json").write_text("{nicht json", "utf-8")
    assert client.get(f"{API}/status").json()["update"]["verfuegbar"] is False


def test_button_writes_request_once(client, app, update_dir):
    write(update_dir, "neueste.json", {"neueste": newer()})
    r = client.post(f"{API}/update")
    assert r.status_code == 202 and r.json()["laeuft"] is True
    assert (app.state.settings.data_dir / "update-anfrage").exists()
    # zweimal drücken startet kein zweites Update
    assert client.post(f"{API}/update").status_code == 409


def test_running_update_blocks_button_until_stale(client, app, update_dir):
    write(update_dir, "neueste.json", {"neueste": newer()})
    now = datetime.now().astimezone()
    write(update_dir, "update.json", {"status": "laeuft", "zeit": now.isoformat()})
    assert client.get(f"{API}/status").json()["update"]["laeuft"] is True
    assert client.post(f"{API}/update").status_code == 409
    # hängengeblieben: nach 30 Minuten ist der Knopf wieder frei
    write(update_dir, "update.json", {"status": "laeuft", "zeit": (now - timedelta(hours=1)).isoformat()})
    assert client.post(f"{API}/update").status_code == 202


def test_button_only_for_adults_and_switchable(client, app, update_dir):
    write(update_dir, "neueste.json", {"neueste": newer()})
    make_person(client, "Anna")
    kid = make_person(client, "Ida", kind="kind")
    assert client.post(f"{API}/update", headers={"X-Delikatessen-Person": str(kid["id"])}).status_code == 403
    app.state.settings.update_button = False
    assert client.get(f"{API}/status").json()["update"]["knopf"] is False
    assert client.post(f"{API}/update").status_code == 409
    assert not (app.state.settings.data_dir / "update-anfrage").exists()
