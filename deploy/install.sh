#!/usr/bin/env bash
# Installiert oder aktualisiert Delikatessen in einem Debian-LXC (N-01).
# Wiederholbar: legt Nutzer, Python-Umgebung und systemd-Dienst an und lässt Vorhandenes stehen.
#
#   sudo ./install.sh                 # neuestes Release von GitHub
#   sudo ./install.sh v0.2.0          # bestimmtes Release
#   sudo ./install.sh --archiv datei  # lokales Release-Archiv, etwa ohne Internet
set -euo pipefail

REPO="${DELIKATESSEN_REPO:-kallelix/Delikatessen}"
BASE=/opt/delikatessen
DATA=/var/lib/delikatessen
BACKUPS=/var/backups/delikatessen
CONF=/etc/delikatessen
USER_NAME=delikatessen

die() { echo "Fehler: $*" >&2; exit 1; }
info() { echo "==> $*"; }

[[ $EUID -eq 0 ]] || die "Bitte mit root-Rechten ausführen"
command -v apt-get >/dev/null || die "Erwartet wird Debian oder Ubuntu"

VERSION=""
ARCHIVE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --archiv) ARCHIVE="$2"; shift 2 ;;
    v*) VERSION="$1"; shift ;;
    *) die "Unbekanntes Argument: $1" ;;
  esac
done

info "Pakete"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv curl ca-certificates sqlite3 >/dev/null
python3 -c 'import sys; assert sys.version_info >= (3, 11)' || die "Python 3.11 oder neuer nötig"

info "Nutzer und Verzeichnisse"
id "$USER_NAME" >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin "$USER_NAME"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 750 "$DATA" "$BACKUPS"
install -d -m 755 "$BASE/releases"
install -d -o root -g "$USER_NAME" -m 750 "$CONF"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [[ -z "$ARCHIVE" ]]; then
  if [[ -z "$VERSION" ]]; then
    VERSION=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
  fi
  info "Lade Release $VERSION"
  URL="https://github.com/$REPO/releases/download/$VERSION/delikatessen-$VERSION.tar.gz"
  curl -fsSL "$URL" -o "$TMP/release.tar.gz"
  curl -fsSL "$URL.sha256" -o "$TMP/release.sha256"
  (cd "$TMP" && echo "$(cut -d' ' -f1 release.sha256)  release.tar.gz" | sha256sum -c --quiet) || die "Prüfsumme stimmt nicht"
  ARCHIVE="$TMP/release.tar.gz"
fi

# ohne die Besitzer aus dem Archiv (Build-Nutzer der CI), sonst gehörte der Programmcode einer fremden UID
tar --no-same-owner -xzf "$ARCHIVE" -C "$TMP"
SRC=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d -name 'delikatessen-*' | head -n1)
[[ -n "$SRC" && -f "$SRC/VERSION" ]] || die "Archiv enthält kein Release"
VERSION=$(cat "$SRC/VERSION")
TARGET="$BASE/releases/$VERSION"

if [[ ! -x "$TARGET/venv/bin/delikatessen" ]]; then
  info "Installiere $VERSION nach $TARGET"
  rm -rf "$TARGET"
  cp -a "$SRC" "$TARGET"
  python3 -m venv "$TARGET/venv"
  # nur Pakete mit passenden Hashes aus der Lockdatei, die App selbst als fertiges Wheel aus dem Release
  "$TARGET/venv/bin/pip" install -q --require-hashes -r "$TARGET/requirements.lock"
  "$TARGET/venv/bin/pip" install -q --no-deps "$TARGET"/wheel/delikatessen-*.whl
  "$TARGET/venv/bin/python" -m compileall -q "$TARGET/venv" >/dev/null || true
  chown -R root:root "$TARGET"
else
  info "$VERSION ist schon installiert"
fi

if [[ ! -f "$CONF/env" ]]; then
  info "Lege $CONF/env an, bitte DELIKATESSEN_TRUSTED_PROXIES prüfen"
  install -o root -g "$USER_NAME" -m 640 "$TARGET/.env.example" "$CONF/env"
fi
if ! grep -qE '^DELIKATESSEN_SECRET_KEY=.+' "$CONF/env"; then
  info "Erzeuge Schlüssel für gespeicherte Zugangsdaten"
  sed -i '/^DELIKATESSEN_SECRET_KEY=/d' "$CONF/env"
  echo "DELIKATESSEN_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> "$CONF/env"
fi

info "Datenbank migrieren"
set -a; source "$CONF/env"; set +a
runuser -u "$USER_NAME" -- env DELIKATESSEN_DATA_DIR="$DELIKATESSEN_DATA_DIR" "$TARGET/venv/bin/delikatessen" migrate

info "Aktiviere $VERSION"
ln -sfn "$TARGET" "$BASE/current.new"
mv -T "$BASE/current.new" "$BASE/current"

install -m 644 "$TARGET/deploy/systemd/delikatessen.service" /etc/systemd/system/
install -m 644 "$TARGET/deploy/systemd/delikatessen-backup.service" /etc/systemd/system/
install -m 644 "$TARGET/deploy/systemd/delikatessen-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now delikatessen-backup.timer >/dev/null
systemctl enable delikatessen.service >/dev/null
systemctl restart delikatessen.service

# Nur die letzten drei Releases behalten
ls -1dt "$BASE"/releases/* 2>/dev/null | tail -n +4 | while read -r old; do
  [[ "$(readlink -f "$BASE/current")" == "$(readlink -f "$old")" ]] || rm -rf "$old"
done

for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/api/v1/status >/dev/null 2>&1; then
    info "Delikatessen $VERSION läuft auf Port 8000"
    exit 0
  fi
  sleep 1
done
die "Dienst antwortet nicht, siehe: journalctl -u delikatessen -n 50"
