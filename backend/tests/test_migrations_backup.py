"""Migrationen (N-14) und Sicherung mit Wiederherstellung (N-03, AK-10)."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from delikatessen import cli
from delikatessen.db import Base, make_engine
from delikatessen.migrate import alembic_config, upgrade
from delikatessen.migrations_filter import include_name
from tests.conftest import make_person, make_recipe


def test_migrate_from_empty_matches_models(tmp_path):
    engine = make_engine(tmp_path / "leer.sqlite3")
    upgrade(engine)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"include_name": include_name})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], diff
    assert "recipe_fts" in inspect(engine).get_table_names()


def test_downgrade_and_upgrade_again(tmp_path):
    engine = make_engine(tmp_path / "rund.sqlite3")
    upgrade(engine)
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "base")
    assert "recipe" not in inspect(engine).get_table_names()
    upgrade(engine)
    upgrade(engine)  # zweimal hintereinander ist harmlos
    assert "recipe" in inspect(engine).get_table_names()


def test_ak10_backup_restore_roundtrip(client, app, settings, tmp_path, monkeypatch):
    import io

    from PIL import Image

    make_person(client, "Anna")
    r = make_recipe(client, "Gratin")
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, "PNG")
    client.post(f"/api/v1/recipes/{r['id']}/image", files={"file": ("a.png", buf.getvalue(), "image/png")})

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    cli.main(["backup", str(tmp_path / "sicherung"), "--keep", "2"])
    backups = sorted((tmp_path / "sicherung").iterdir())
    assert len(backups) == 1

    # in einen leeren Container zurückspielen
    empty = settings.model_copy(update={"data_dir": tmp_path / "neu"})
    monkeypatch.setattr(cli, "get_settings", lambda: empty)
    cli.main(["restore", str(backups[0])])

    def snapshot(db_path):
        engine = make_engine(db_path)
        with engine.connect() as conn:
            return {
                t: conn.execute(text(f"SELECT * FROM {t} ORDER BY 1")).all()
                for t in ("person", "recipe", "recipe_ingredient", "ingredient", "plan_week")
            }

    assert snapshot(empty.db_path) == snapshot(settings.db_path)
    assert sorted(p.name for p in empty.image_dir.iterdir()) == sorted(p.name for p in settings.image_dir.iterdir())
    # die Suche funktioniert nach der Wiederherstellung
    from fastapi.testclient import TestClient

    from delikatessen.main import create_app

    with TestClient(create_app(empty)) as restored:
        assert [x["title"] for x in restored.get("/api/v1/recipes", params={"q": "gratin"}).json()] == ["Gratin"]


def test_backup_keeps_only_newest(settings, tmp_path, monkeypatch, app):
    import time

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    for _ in range(3):
        cli.main(["backup", str(tmp_path / "b"), "--keep", "2"])
        time.sleep(1.05)
    assert len(list((tmp_path / "b").iterdir())) == 2
