#!/usr/bin/env bash
# Update auf Knopfdruck aus der App ("Mehr" › "Status der Dienste"). Startet als root über
# delikatessen-update.path, sobald die App die Datei update-anfrage anlegt.
#
# Installiert immer das neueste Release, die App kann weder Version noch Parameter wählen.
# Schlägt das Update fehl, stellt das Skript das vorige Release und die Sicherung von eben zurück.
set -uo pipefail

REPO="${DELIKATESSEN_REPO:-kallelix/Delikatessen}"
BASE=/opt/delikatessen
DATA=/var/lib/delikatessen
BACKUPS=/var/backups/delikatessen
STATE="${DELIKATESSEN_UPDATE_DIR:-/var/lib/delikatessen-update}"
REQUEST="$DATA/update-anfrage"
DIR=$(cd "$(dirname "$0")" && pwd)

# Die Anforderung zuerst entfernen, sonst startet die Path-Unit gleich wieder. rm folgt keinem Symlink,
# und der Inhalt der Datei wird nie gelesen.
rm -f -- "$REQUEST"

PREV=$(readlink -f "$BASE/current")
FROM=$(cat "$PREV/VERSION" 2>/dev/null || basename "$PREV")

state() { python3 "$DIR/update-zustand.py" status "$STATE/update.json" "$1" "$2" "$FROM" "${3:-}"; }

healthy() {
  for _ in $(seq 1 30); do
    curl -fsS --max-time 3 http://127.0.0.1:8000/api/v1/status >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

LATEST=$(curl -fsSL --max-time 30 "https://api.github.com/repos/$REPO/releases/latest" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])') || LATEST=""
if [[ ! "$LATEST" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  state fehler "GitHub ist nicht erreichbar, es wurde nichts geändert."
  exit 1
fi
if [[ "$LATEST" == "$FROM" ]]; then
  state aktuell "$FROM ist schon die neueste Version."
  exit 0
fi

state laeuft "Update auf $LATEST läuft." "$LATEST"
START=$(date +%s)
echo "==> Update von $FROM auf $LATEST"
if bash "$DIR/update.sh" "$LATEST"; then
  state fertig "Version $LATEST ist installiert." "$LATEST"
  exit 0
fi

echo "==> Update fehlgeschlagen, stelle $FROM wieder her"
# Sicherung, die update.sh eben vor allen Änderungen angelegt hat. Ohne sie wurde nichts geändert.
BACKUP=$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d -name 'delikatessen_*' -newermt "@$START" | sort | tail -n1)
if [[ "$(readlink -f "$BASE/current")" != "$PREV" ]] || ! healthy; then
  systemctl stop delikatessen.service
  ln -sfn "$PREV" "$BASE/current.new" && mv -T "$BASE/current.new" "$BASE/current"
  if [[ -n "$BACKUP" ]]; then
    set -a; source /etc/delikatessen/env; set +a
    runuser -u delikatessen -- env DELIKATESSEN_DATA_DIR="$DELIKATESSEN_DATA_DIR" \
      "$PREV/venv/bin/delikatessen" restore "$BACKUP"
  fi
  systemctl start delikatessen.service
fi
if healthy; then
  state fehler "Update auf $LATEST fehlgeschlagen, $FROM läuft wieder. Details: journalctl -u delikatessen-update" "$LATEST"
else
  state fehler "Update auf $LATEST fehlgeschlagen, und die App startet nicht. Bitte per SSH prüfen: journalctl -u delikatessen-update" "$LATEST"
fi
exit 1
