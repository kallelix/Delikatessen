"""Link-Import: AK-06 mit festem Seitenset, Vorschau, Übernahme und SSRF-Schutz."""

import functools
import http.server
import threading
import time
from pathlib import Path

import pytest

from delikatessen.netguard import FetchError, fetch

API = "/api/v1"
FIXTURES = Path(__file__).parent / "fixtures"
PAGES = sorted((FIXTURES / "rezeptseiten").glob("*.html"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/weiter":
            self.send_response(302)
            self.send_header("Location", "/rezeptseiten/01_einfach.html")
            self.end_headers()
            return
        if self.path == "/riesig":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"x" * 6_000_000)
            return
        super().do_GET()


@pytest.fixture(scope="module")
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(FIXTURES)))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def run_import(client, url, timeout=20):
    job = client.post(f"{API}/imports", json={"kind": "link", "url": url}).json()
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"{API}/imports/{job['id']}").json()
        if job["status"] not in ("wartet", "laeuft"):
            return job
        time.sleep(0.05)
    raise AssertionError("Import hängt")


def test_ak06_fixed_page_set(client, server):
    assert len(PAGES) == 10
    ok = []
    for page in PAGES:
        job = run_import(client, f"{server}/rezeptseiten/{page.name}")
        res = job["result"] or {}
        lines = res.get("ingredients") or []
        if job["status"] == "fertig" and res.get("title") and lines and all(i["name"] for i in lines):
            ok.append(page.name)
    assert len(ok) >= 9, f"nur {ok}"


def test_preview_content(client, server):
    job = run_import(client, f"{server}/rezeptseiten/01_einfach.html")
    res = job["result"]
    assert res["title"] == "Kartoffelgratin" and res["servings"] == 4 and res["duration_min"] == 70
    assert res["steps"][0].startswith("Kartoffeln schälen")
    first = res["ingredients"][0]
    assert (first["amount"], first["unit"], first["name"]) == (1.2, "kg", "Kartoffeln")
    assert first["ingredient_id"] is not None  # über Normalisierung zugeordnet
    assert first["ingredient_name"] == "Kartoffel"  # Katalogname für die Vorschau
    gouda = res["ingredients"][2]
    assert gouda["note"] == "gerieben" and gouda["ingredient_id"] is not None
    assert res["image_url"] == "https://example.org/gratin.jpg"


def test_iso_page_and_entities(client, server):
    job = run_import(client, f"{server}/rezeptseiten/08_iso.html")
    assert job["result"]["title"] == "Gulasch nach Großmutter"
    job = run_import(client, f"{server}/rezeptseiten/07_entities.html")
    assert "Käsespätzle" in job["result"]["title"]


def test_redirect_is_followed(client, server):
    job = run_import(client, f"{server}/weiter")
    assert job["status"] == "fertig" and job["result"]["source_url"].endswith("01_einfach.html")


def test_page_without_schema(client, server):
    job = run_import(client, f"{server}/ohne_schema.html")
    assert job["status"] == "ohne_schema"
    assert job["result"]["title"] == "Omas Nudelauflauf | Blog"


def test_accept_creates_recipe_and_marks_job(client, server):
    job = run_import(client, f"{server}/rezeptseiten/02_graph.html")
    res = job["result"]
    body = {
        "recipe": {
            "title": res["title"],
            "servings": res["servings"],
            "size": "haupt",
            "steps": res["steps"],
            "source_url": res["source_url"],
            "ingredients": [
                {k: i[k] for k in ("amount", "unit", "name", "note", "ingredient_id")} for i in res["ingredients"]
            ],
        }
    }
    r = client.post(f"{API}/imports/{job['id']}/accept", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["title"] == "Spaghetti Bolognese"
    assert client.get(f"{API}/imports/{job['id']}").json()["status"] == "uebernommen"
    assert client.post(f"{API}/imports/{job['id']}/accept", json=body).status_code == 409


def test_errors_are_reported(client, server):
    job = run_import(client, f"{server}/gibtsnicht.html")
    assert job["status"] == "fehler" and "404" in job["error"]
    job = run_import(client, f"{server}/riesig")
    assert job["status"] == "fehler" and "groß" in job["error"]
    r = client.post(f"{API}/imports", json={"kind": "link", "url": "file:///etc/passwd"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:8000/",
        "http://10.1.2.3/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "ftp://example.org/",
    ],
)
def test_ssrf_blocked(url):
    with pytest.raises(FetchError):
        fetch(url, timeout=2, max_bytes=1000, allow_private=False)


def test_ssrf_blocked_after_redirect(server):
    # Weiterleitung auf eine interne Adresse wird gesperrt, auch wenn die erste Adresse erlaubt war
    import delikatessen.netguard as ng

    calls = []
    original = ng._check_url

    def check(url, allow_private):
        calls.append(url)
        original(url, allow_private=len(calls) == 1)

    ng._check_url = check
    try:
        with pytest.raises(FetchError, match="Interne"):
            fetch(f"{server}/weiter", timeout=2, max_bytes=100_000)
    finally:
        ng._check_url = original


def _preview(db, *lines):
    from delikatessen.importer import preview_ingredients

    return [
        (i["name"], i["ingredient_name"], i["amount"], i["unit"], i["note"])
        for i in preview_ingredients(db, list(lines))
    ]


def test_combined_lines_are_split(db):
    assert _preview(db, "Salz und Pfeffer") == [
        ("Salz", "Salz", None, None, None),
        ("Pfeffer", "Pfeffer", None, None, None),
    ]
    assert _preview(db, "Pfeffer & Salz") == [
        ("Pfeffer", "Pfeffer", None, None, None),
        ("Salz", "Salz", None, None, None),
    ]
    # Komma, beschreibende Wörter vor der Zutat, Zusatz in Klammern
    assert _preview(db, "Salz, frisch gemahlener Pfeffer und Muskat (nach Geschmack)") == [
        ("Salz", "Salz", None, None, "nach Geschmack"),
        ("Pfeffer", "Pfeffer", None, None, "nach Geschmack, frisch gemahlener"),
        ("Muskat", "Muskatnuss", None, None, "nach Geschmack"),
    ]
    # Prise gilt je Zutat, Gramm nur zusammen
    assert _preview(db, "1 Prise Salz und Pfeffer") == [
        ("Salz", "Salz", 1, "Prise", None),
        ("Pfeffer", "Pfeffer", 1, "Prise", None),
    ]
    assert _preview(db, "300 g Erbsen und Möhren") == [
        ("Erbsen", "Erbsen", None, None, "zusammen 300 g"),
        ("Möhren", "Karotte", None, None, "zusammen 300 g"),
    ]


def test_descriptors_and_headings(db):
    # Wörter aus der festen Liste fallen beim Zuordnen weg und werden Zusatz
    assert _preview(db, "1 kleine Zwiebel(n)") == [("Zwiebel", "Zwiebel", 1, None, "kleine")]
    assert _preview(db, "2 m.-große Kartoffeln, geschält") == [
        ("Kartoffeln", "Kartoffel", 2, None, "m.-große, geschält")
    ]
    # andere Wörter nicht: saure Sahne ist keine Sahne
    assert _preview(db, "200 g saure Sahne")[0][1] == "Saure Sahne"
    assert _preview(db, "1 Becher geschlagene Sahne")[0][1] is None
    # Zwischenüberschriften sind keine Zutaten
    assert _preview(db, "Für den Teig:", "200 g Mehl", "Soße:", "1 Zwiebel") == [
        ("Mehl", "Mehl", 200, "g", None),
        ("Zwiebel", "Zwiebel", 1, None, None),
    ]


def test_step_numbers_are_not_steps():
    from delikatessen.importer import clean_steps

    steps = [
        "Schritt 1",
        "Zwiebeln schneiden.",
        "Schritt 2:",
        "Anbraten.",
        "3.",
        "Step 4: Servieren.",
        "Schritt für Schritt rühren.",
    ]
    assert clean_steps(steps) == ["Zwiebeln schneiden.", "Anbraten.", "Servieren.", "Schritt für Schritt rühren."]


def test_lines_that_stay_whole(db):
    # Zusatz nach dem Komma ist keine Zutat
    assert _preview(db, "2 Zehen Knoblauch, gehackt") == [("Knoblauch", "Knoblauch", 2, "Zehe", "gehackt")]
    # Alternativen werden nicht getrennt
    assert len(_preview(db, "Butter oder Margarine")) == 1
    assert len(_preview(db, "Öl/Butter")) == 1
    # nur ein Teil bekannt: lieber ganz lassen und von Hand zuordnen
    assert _preview(db, "Salz und Drachenfrucht") == [("Salz und Drachenfrucht", None, None, None, None)]
    # ganzer Name im Katalog: nicht zerlegen
    assert _preview(db, "Passierte Tomaten") == [("Passierte Tomaten", "Passierte Tomaten", None, None, None)]


def test_creative_page(client, server):
    """Testseite mit Zwischenüberschriften, Mengen hinter dem Namen und "Schritt 1" als eigener Zeile."""
    job = run_import(client, f"{server}/kreativ.html")
    assert job["status"] == "fertig", job
    res = job["result"]
    assert res["steps"] == [
        "Mehl, Eier und Butter zu einem Teig kneten.",
        "Zwiebel, Drachenfrucht und Mondbohnen hacken, einfüllen und backen.",
    ]
    rows = [(i["name"], i["ingredient_name"], i["amount"], i["unit"], i["note"]) for i in res["ingredients"]]
    assert rows == [
        ("Mehl", "Mehl", 250, "g", None),
        ("Ei", "Ei", 2, None, None),
        ("Butter", "Butter", 50, "g", None),
        ("Zwiebel", "Zwiebel", 1, None, "kleine"),
        ("Drachenfrucht", None, 1, "Stück", None),
        ("Mondbohnen", None, 100, "g", None),
        ("Salz", "Salz", None, None, "nach Belieben"),
    ]


def test_lines_from_iglo(db):
    """Zeilen wie auf iglo.de (15.11.2026): Einheit pcs, Großschreibung, Überschrift mit Menge, Alternativen."""
    assert _preview(
        db,
        "1 pcs Fischstäbchen",
        "1 pcs Für Den Kartoffelbrei:",
        "0.5 kg Kartoffeln Mehligkochend Oder Vorwiegend Festkochend",
        "100 ml Sahne Oder Milch",
        "0.5 TL Salz Oder Nach Geschmack",
    ) == [
        ("Fischstäbchen", "Fischstäbchen", 1, "Stück", None),
        ("Kartoffeln", "Kartoffel", 0.5, "kg", "Mehligkochend, oder Vorwiegend Festkochend"),
        ("Sahne", "Sahne", 100, "ml", "oder Milch"),
        ("Salz", "Salz", 0.5, "TL", "Nach Geschmack"),
    ]
