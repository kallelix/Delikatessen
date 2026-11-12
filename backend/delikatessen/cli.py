"""Kommandozeile: serve, migrate, backup, restore, ki-pruefen."""

from __future__ import annotations

import argparse
import logging
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime
from pathlib import Path

from .config import get_settings

VAPID_FILE = "vapid_private.pem"


def cmd_serve(args) -> None:
    import uvicorn

    from .main import create_app

    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=args.host,
        port=args.port,
        proxy_headers=False,  # X-Forwarded-For wertet die App selbst und nur vom nginx-LXC aus
        access_log=False,  # keine Rezepttexte oder Links im Log (Abschnitt 11)
    )


def cmd_migrate(_args) -> None:
    from .db import Database
    from .migrate import upgrade

    settings = get_settings()
    db = Database(settings.db_path)
    upgrade(db.engine)
    print(f"Datenbank {settings.db_path} ist aktuell")


def cmd_backup(args) -> None:
    """Sicherung der Datenbank mit der SQLite-Backup-Schnittstelle (wie sqlite3 .backup) plus Bilder."""
    settings = get_settings()
    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = target / f"delikatessen_{stamp}"
    dest.mkdir()
    src = sqlite3.connect(settings.db_path)
    out = sqlite3.connect(dest / "delikatessen.sqlite3")
    with out:
        src.backup(out)
    src.close()
    out.close()
    with tarfile.open(dest / "bilder.tar", "w") as tar:
        if settings.image_dir.is_dir():
            tar.add(settings.image_dir, arcname="bilder")
    # Schlüssel für Web Push: ohne ihn müssten sich alle Geräte nach einer Wiederherstellung neu anmelden
    vapid = settings.data_dir / VAPID_FILE
    if vapid.is_file():
        shutil.copy2(vapid, dest / VAPID_FILE)
        (dest / VAPID_FILE).chmod(0o600)
    backups = sorted(p for p in target.glob("delikatessen_*") if p.is_dir())
    for old in backups[: max(0, len(backups) - args.keep)]:
        shutil.rmtree(old)
    print(f"Sicherung geschrieben: {dest}")


def cmd_restore(args) -> None:
    """Spielt eine Sicherung zurück. Der Dienst muss dafür gestoppt sein."""
    settings = get_settings()
    src = Path(args.source)
    db_file = src / "delikatessen.sqlite3"
    if not db_file.is_file():
        sys.exit(f"Keine Datenbank in {src}")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(f"{settings.db_path}{suffix}").unlink(missing_ok=True)
    shutil.copy2(db_file, settings.db_path)
    tar_path = src / "bilder.tar"
    if tar_path.is_file():
        if settings.image_dir.exists():
            shutil.rmtree(settings.image_dir)
        with tarfile.open(tar_path) as tar:
            _safe_extract(tar, settings.data_dir)
    if (src / VAPID_FILE).is_file():
        shutil.copy2(src / VAPID_FILE, settings.data_dir / VAPID_FILE)
        (settings.data_dir / VAPID_FILE).chmod(0o600)
    print(f"Sicherung {src} nach {settings.data_dir} zurückgespielt")


def _safe_extract(tar: tarfile.TarFile, target: Path) -> None:
    """Entpackt nur normale Dateien und Ordner unterhalb von target."""
    if hasattr(tarfile, "data_filter"):
        tar.extractall(target, filter="data")
        return
    root = target.resolve()
    for member in tar.getmembers():
        dest = (target / member.name).resolve()
        if not (member.isfile() or member.isdir()) or not dest.is_relative_to(root):
            sys.exit(f"Unerwarteter Eintrag in der Sicherung: {member.name}")
    tar.extractall(target)


SAMPLE = """Kartoffelsuppe für 4 Personen, 40 Minuten
800 g Kartoffeln
1 Zwiebel, gewürfelt
1 l Gemüsebrühe
Salz und Pfeffer
Zwiebel andünsten, Kartoffeln und Brühe dazu, 20 Minuten kochen, pürieren, abschmecken."""


def cmd_ki_pruefen(_args) -> None:
    """AK-24: kommt die strukturierte Antwort über das Gateway im festgelegten Schema an?"""
    from . import ki

    settings = get_settings()
    if not settings.ki_configured:
        sys.exit("DELIKATESSEN_KI_BASE_URL und DELIKATESSEN_KI_API_KEY fehlen in /etc/delikatessen/env")
    print(f"Gateway {settings.ki_base_url}, Modell-Alias {settings.ki_model}, Ausgabe {settings.ki_structured}")
    try:
        recipe = ki.KiClient(settings).extract(text=SAMPLE, tag_names=["vegetarisch"])
    except ki.KiError as e:
        sys.exit(f"Fehlgeschlagen: {e}")
    names = [i.name for i in recipe.ingredients]
    print(f"Antwort im Schema: {recipe.title}, {recipe.servings} Portionen, {recipe.duration_min} Minuten")
    print(f"Zutaten: {', '.join(names)}")
    ok = recipe.found and recipe.servings == 4 and {"Salz", "Pfeffer"} <= set(names) and len(names) >= 5
    print("AK-24 erfüllt" if ok else "Antwort im Schema, aber inhaltlich unerwartet, bitte ansehen")
    budget = ki.budget(settings)
    if budget:
        print(f"Budget: {budget.spend:.2f} von {budget.max_budget} USD")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # keine abgerufenen Rezeptadressen und keine Migrationsdetails im Journal (Abschnitt 11)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="delikatessen")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("serve", help="Server starten")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("migrate", help="Datenbank migrieren")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("backup", help="Datenbank und Bilder sichern")
    p.add_argument("target")
    p.add_argument("--keep", type=int, default=14)
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="Sicherung zurückspielen (Dienst vorher stoppen)")
    p.add_argument("source")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("ki-pruefen", help="KI-Gateway mit einem Beispielrezept prüfen (AK-24)")
    p.set_defaults(func=cmd_ki_pruefen)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
