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
# Das Skript kann aus einem älteren Release stammen: install.sh des Ziel-Releases verwenden
if [[ -n "${DELIKATESSEN_LOCAL:-}" || "${1:-}" == --* ]]; then
  exec bash "$INSTALL" "$@"
fi
REPO="${DELIKATESSEN_REPO:-kallelix/Delikatessen}"
VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  VERSION=$(curl -fsSL --max-time 30 "https://api.github.com/repos/$REPO/releases/latest" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
fi
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Ungültige Version: $VERSION" >&2; exit 1; }

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
# install.sh vom Tag des Releases, nicht vom Entwicklungsstand auf main
if ! curl -fsSL --max-time 30 "https://raw.githubusercontent.com/$REPO/$VERSION/deploy/install.sh" -o "$TMP"; then
  echo "install.sh von $VERSION nicht erreichbar, nehme die installierte" >&2
  cp "$INSTALL" "$TMP"
fi
bash "$TMP" "$VERSION"
echo "Rückweg bei Problemen: sudo ln -sfn /opt/delikatessen/releases/<alte Version> /opt/delikatessen/current"
echo "                        und die Sicherung aus /var/backups/delikatessen zurückspielen (docs/betrieb.md)"
