#!/usr/bin/env python3
"""Schreibt den Update-Stand für die App, atomar und nur für root und die Gruppe delikatessen lesbar.

    update-zustand.py neueste <datei>                       # Antwort von GitHub /releases/latest auf stdin
    update-zustand.py status <datei> <status> <meldung> <von> [<nach>]

Die App liest die Dateien nur. Das Verzeichnis gehört root, damit der App-Nutzer dort nichts
umbiegen kann, in das root später schreibt.
"""

import grp
import json
import os
import sys
import tempfile
from datetime import datetime


def write(path: str, data: dict) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".zustand-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        try:
            os.chown(tmp, 0, grp.getgrnam("delikatessen").gr_gid)
        except (KeyError, PermissionError):
            pass  # ohne Gruppe oder ohne root, etwa bei einem Test
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "neueste":
        release = json.load(sys.stdin)
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag.startswith("v"):
            print("Antwort von GitHub ohne gültiges Release", file=sys.stderr)
            return 1
        write(argv[1], {"neueste": tag, "url": release.get("html_url"), "geprueft": now()})
        return 0
    if len(argv) >= 5 and argv[0] == "status":
        path, status, message, frm = argv[1:5]
        write(
            path,
            {
                "status": status,
                "meldung": message,
                "von": frm,
                "nach": argv[5] if len(argv) > 5 else None,
                "zeit": now(),
            },
        )
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
