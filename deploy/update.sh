#!/usr/bin/env bash
# Update ohne Datenverlust (N-14): sichert zuerst, holt das Release-Tag, migriert und startet neu.
#
#   sudo ./update.sh            # neuestes Release
#   sudo ./update.sh v0.2.0     # bestimmtes Release
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Bitte mit root-Rechten ausführen" >&2; exit 1; }

echo "==> Sicherung vor dem Update"
systemctl start delikatessen-backup.service
systemctl is-failed --quiet delikatessen-backup.service && { echo "Sicherung fehlgeschlagen, Update abgebrochen" >&2; exit 1; }

DIR=$(cd "$(dirname "$0")" && pwd)
INSTALL="$DIR/install.sh"
# Das Skript kann aus einem älteren Release stammen: immer die neueste install.sh verwenden
if [[ -n "${DELIKATESSEN_LOCAL:-}" ]]; then
  exec "$INSTALL" "$@"
fi
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
REPO="${DELIKATESSEN_REPO:-kallelix/Delikatessen}"
REF="${1:-main}"
curl -fsSL "https://raw.githubusercontent.com/$REPO/$REF/deploy/install.sh" -o "$TMP" || cp "$INSTALL" "$TMP"
bash "$TMP" "$@"
echo "Rückweg bei Problemen: sudo ln -sfn /opt/delikatessen/releases/<alte Version> /opt/delikatessen/current"
echo "                        und die Sicherung aus /var/backups/delikatessen zurückspielen (docs/betrieb.md)"
