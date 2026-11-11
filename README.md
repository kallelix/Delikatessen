# Delikatessen

Delikatessen erstellt für die Familie per Knopfdruck einen Wochenplan aus ihren Lieblingsessen und macht daraus die Einkaufsliste. Die App läuft selbst gehostet in einem LXC-Container auf Proxmox und wird als installierbare Web-App am Android-Smartphone bedient.

- [Lastenheft](docs/lastenheft.md): was die App leisten soll
- [Pflichtenheft](docs/pflichtenheft.md): wie sie es umsetzt
- [Betrieb](docs/betrieb.md): Installation, Updates, Sicherung, Abnahme auf dem Gerät

## Stand

Stufe 1 (Kern) ist umgesetzt: Rezepte mit Fotos und Suche, Import per Link und Teilen-Menü, Zutatenkatalog, Familie mit No-go-Zutaten, Bewertungen und Rangliste, Wochenplan mit Neu-Vorschlag, Fixieren und Zusatzplätzen, Einkaufsliste in der App, Offline-Lesen der Woche. Stufe 2 bringt Bring!, Import per Foto und Sprache, KI-Auswertung und den Donnerstagslauf.

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `backend/` | Python 3.11+, FastAPI, SQLite mit Alembic, Tests mit pytest |
| `frontend/` | React, TypeScript, Vite, eigener Service Worker, Tests mit Vitest und Playwright |
| `deploy/` | Installations- und Update-Skript, systemd-Units, nginx-Beispiel |

## Entwicklung

```bash
# Backend
cd backend
python -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.lock   # Windows: .venv\Scripts\...
.venv/bin/pip install --no-deps -e .
.venv/bin/pytest
DELIKATESSEN_DATA_DIR=./data .venv/bin/delikatessen serve --port 8000

# Frontend (zweites Terminal), leitet /api an Port 8000 weiter
cd frontend
npm ci
npm run dev
npm test               # Einheitentests
npm run build && npx playwright test   # Oberflächentests gegen den echten Server
```

Die Schnittstelle ist unter `/api/docs` beschrieben. Lockdateien neu erzeugen: `uv pip compile pyproject.toml --universal --generate-hashes --python-version 3.11 -o requirements.lock` (und mit `--extra dev` nach `requirements-dev.lock`).

Konfiguration nur über Umgebungsvariablen, siehe [.env.example](.env.example). Zugangsdaten, Domains und Familiendaten gehören nicht ins Repository. Ein Secret-Scan läuft in der CI und lokal über `pre-commit install`.

## Lizenz

[MIT](LICENSE)
