#!/usr/bin/env bash
# Prüft, ob es ein neueres Release gibt, und schreibt das Ergebnis für den Hinweis in der App.
# Läuft täglich über delikatessen-update-check.timer. Die App selbst fragt GitHub nie.
set -euo pipefail

REPO="${DELIKATESSEN_REPO:-kallelix/Delikatessen}"
STATE="${DELIKATESSEN_UPDATE_DIR:-/var/lib/delikatessen-update}"
DIR=$(cd "$(dirname "$0")" && pwd)

curl -fsSL --max-time 30 -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/releases/latest" \
  | python3 "$DIR/update-zustand.py" neueste "$STATE/neueste.json"
