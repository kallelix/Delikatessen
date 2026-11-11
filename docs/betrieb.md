# Delikatessen – Betrieb

Stand: 2026-11-11

Stufe 1 braucht einen neuen Debian-LXC und den vorhandenen nginx-LXC mit NetBird. Nichts wird ins Internet freigegeben.

## 1. Container anlegen

| Einstellung | Wert |
| --- | --- |
| Vorlage | Debian 12 oder 13, unprivilegiert |
| Ressourcen | 2 vCPU, 2 GB RAM, 20 GB Speicher (N-02) |
| Netz | feste Adresse im Heimnetz |
| Firewall | eingehend nur Port 8000 vom nginx-LXC |

Proxmox-Backups des Containers zusätzlich einplanen. Sie ersetzen nicht die tägliche Sicherung der App, weil die auch einzelne Tage zurückholen kann.

## 2. Installieren

```bash
curl -fsSLO https://raw.githubusercontent.com/kallelix/Delikatessen/main/deploy/install.sh
less install.sh          # vorher lesen
sudo bash install.sh     # neuestes Release, oder: sudo bash install.sh v0.1.0
```

Das Skript ist wiederholbar. Es legt den Nutzer `delikatessen`, die Python-Umgebung unter `/opt/delikatessen/releases/<Version>`, die Konfiguration `/etc/delikatessen/env`, den Dienst und den Sicherungs-Timer an. Pakete installiert es nur mit den Hashes aus der Lockdatei.

Danach in `/etc/delikatessen/env` die Adresse des nginx-LXC bei `DELIKATESSEN_TRUSTED_PROXIES` eintragen und `sudo systemctl restart delikatessen` ausführen. Nur von dieser Adresse akzeptiert die App `X-Forwarded-For`, sonst ließe sich die Profilzuordnung über die NetBird-IP fälschen.

| Pfad | Inhalt |
| --- | --- |
| `/var/lib/delikatessen` | Datenbank `delikatessen.sqlite3` und Ordner `bilder` |
| `/var/backups/delikatessen` | tägliche Sicherungen, 14 Tage |
| `/etc/delikatessen/env` | Konfiguration, nicht im Repository |
| `/opt/delikatessen/current` | aktives Release |

Protokolle: `journalctl -u delikatessen`. Rezepttexte, Bilder und abgerufene Links landen dort nicht.

## 3. nginx und NetBird

Vorlage: [deploy/nginx-delikatessen.conf.example](../deploy/nginx-delikatessen.conf.example). Wichtig sind `proxy_set_header X-Forwarded-For $remote_addr` und `client_max_body_size 16m` für Fotos. Das Zertifikat kommt per Let's Encrypt mit DNS-Challenge, HTTPS ist für Installation, Kamera und Teilen-Menü Pflicht (N-04).

In NetBird lässt eine Access Policy nur die Familiengeräte auf Port 443 des nginx-LXC zu. Die Trennung von Erwachsenen und Kindern in der App ist bewusst nur ein Bedienschutz (N-09).

Optional ordnet die App ein Gerät über seine NetBird-IP automatisch einem Profil zu: unter „Mehr“ › „Familie“ bei der Person eintragen.

## 4. Updates

```bash
sudo bash /opt/delikatessen/current/deploy/update.sh          # neuestes Release
sudo bash /opt/delikatessen/current/deploy/update.sh v0.2.0   # bestimmtes Release
```

Das Update sichert zuerst, installiert das Release daneben, migriert die Datenbank und schaltet dann um (N-14). Die letzten drei Releases bleiben liegen. Ein Rückweg auf ein älteres Release braucht auch die Sicherung von vor dem Update, weil die Datenbank schon migriert ist (Abschnitt 5).

Ein Release entsteht, wenn ein Tag `vX.Y.Z` gepusht wird, der zur Version in `backend/pyproject.toml` passt. Die CI baut dann das Archiv mit Prüfsumme.

## 5. Sicherung und Wiederherstellung (N-03, AK-10)

Der Timer `delikatessen-backup.timer` sichert täglich um 3:30 Uhr Datenbank und Bilder nach `/var/backups/delikatessen/delikatessen_<Datum>`. Sofort sichern: `sudo systemctl start delikatessen-backup.service`.

**Wiederherstellen:**

```bash
sudo systemctl stop delikatessen
sudo runuser -u delikatessen -- env DELIKATESSEN_DATA_DIR=/var/lib/delikatessen \
  /opt/delikatessen/current/venv/bin/delikatessen restore /var/backups/delikatessen/delikatessen_<Datum>
sudo systemctl start delikatessen
```

**Einmaliger Test (Abnahme AK-10):** Einen frischen Container nach Abschnitt 2 installieren, eine Sicherung aus dem Produktivcontainer hineinkopieren, wie oben zurückspielen und prüfen:

- [ ] Anzahl Rezepte, Personen und Planwochen stimmt
- [ ] Fotos werden angezeigt
- [ ] Suche findet ein bekanntes Rezept
- [ ] Datum des Tests hier eintragen: ____

Der automatische Test `backend/tests/test_migrations_backup.py` prüft denselben Weg bei jedem CI-Lauf.

## 6. Abnahme auf dem Gerät

Teilen, Push, Wake Lock und Offline lassen sich nur auf echten Android-Geräten zuverlässig prüfen (Pflichtenheft Abschnitt 12). Für Stufe 1 auf jedem Familiengerät in Chrome:

- [ ] App über „Zum Startbildschirm hinzufügen“ installieren, sie startet ohne Adressleiste
- [ ] Profil wählen, nach Neustart der App ist es noch gewählt
- [ ] AK-07: In Chrome eine Rezeptseite öffnen, „Teilen“ › „Delikatessen“: die Importvorschau öffnet sich
- [ ] Kochansicht: Display geht während des Kochens nicht aus, auch nach kurzem Wechsel in eine andere App
- [ ] AK-09: Plan einmal öffnen, Flugmodus an, App neu starten: Plan und Rezepte der Woche sind lesbar
- [ ] Rezeptfoto mit der Kamera aufnehmen
- [ ] Einkaufsliste als Text teilen, etwa in einen Messenger
- [ ] AK-11: Von außen (Mobilfunk ohne NetBird) ist die App nicht erreichbar, ein Portscan auf die öffentliche Adresse findet nichts

**AK-12:** Stufe 1 gilt als abgenommen, wenn die Familie zwei Wochen mit der App geplant hat. Erst danach beginnt Stufe 2.

## 7. Stand der Abnahmekriterien Stufe 1

| ID | Prüfung | Stand |
| --- | --- | --- |
| AK-01 | `test_ak01_200_recipes_under_3_seconds` | automatisch |
| AK-02 | `test_ak02_no_nogo_in_1000_plans` | automatisch |
| AK-03 | `test_ak03_regenerate_keeps_pinned_and_cancelled` | automatisch |
| AK-04 | `test_ak04_few_recipes_repeat_and_empty_reason` | automatisch |
| AK-05 | `test_ak05_weekend_one_main_per_day` | automatisch |
| AK-06 | `test_ak06_fixed_page_set` mit 10 Testseiten | automatisch, mit echten gespeicherten Seiten ergänzen |
| AK-07 | Playwright „Teilen-Menü öffnet die Importvorschau“ | automatisch, plus Gerät |
| AK-08 | `test_ak08_fixed_case` | automatisch |
| AK-09 | Playwright „ohne Netz lesbar“ | automatisch, plus Gerät |
| AK-10 | `test_ak10_backup_restore_roundtrip` | automatisch, plus einmal im Container |
| AK-11 | Portscan | Gerät und Netz |
| AK-12 | zwei Wochen Familienbetrieb | offen |
| AK-13 | `test_ak13_extra_lunch_slots_and_cancelled_not_in_shopping` | automatisch |
| AK-14 | `test_ak14_new_suggestion_never_repeats` | automatisch |

Für AK-06 lohnt es sich, zehn echte Rezeptseiten, die die Familie nutzt, als HTML unter `backend/tests/fixtures/rezeptseiten/` abzulegen. Wegen der Urheberrechte bleiben sie besser außerhalb des öffentlichen Repositorys oder werden auf das Schema-Markup gekürzt.
