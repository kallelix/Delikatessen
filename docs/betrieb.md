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
sudo bash install.sh     # neuestes Release, oder: sudo bash install.sh v0.2.0
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

Vorlage: [deploy/nginx-delikatessen.conf.example](../deploy/nginx-delikatessen.conf.example). Wichtig sind `allow`/`deny` für das NetBird-Netz, `proxy_set_header X-Forwarded-For` und `client_max_body_size 64m` für bis zu 4 Fotos. Ein vorhandenes Wildcard-Zertifikat passt. HTTPS ist auch im NetBird Pflicht, weil der Browser sonst Installation, Offline-Lesen, Teilen-Menü, Push, Diktat und „Bildschirm bleibt an“ sperrt (N-04).

**Nur im NetBird erreichbar**, auch wenn derselbe nginx andere Seiten ins Internet ausliefert:

- Im Server-Block nur das NetBird-Netz zulassen (`allow`/`deny` in der Vorlage). Das setzt voraus, dass der nginx-LXC selbst NetBird-Peer ist. Kommen die Geräte über einen Routing-Peer mit Masquerade, sieht nginx nur dessen Adresse.
- Der Name muss für die Geräte auf die NetBird-IP des nginx-LXC zeigen, nicht auf die öffentliche Adresse, sonst kommt 403. Am einfachsten ein eigener A-Record für den Namen, er hat Vorrang vor einem Wildcard-Eintrag. Alternativ ein DNS-Eintrag in NetBird.
- In NetBird lässt eine Access Policy nur die Familiengeräte auf Port 443 des nginx-LXC zu.
- Im delikatessen-LXC Port 8000 nur vom nginx-LXC zulassen (Proxmox-Firewall), sonst ginge es im Heimnetz an nginx vorbei per HTTP.

Die Trennung von Erwachsenen und Kindern in der App ist bewusst nur ein Bedienschutz (N-09).

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

## 7. Stand der Abnahmekriterien

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
| AK-20 | `test_ak20_amounts_and_no_duplicates`, `test_ak20_bought_at_home_and_reactivated` | automatisch gegen eine Bring!-Attrappe, plus Gerät |
| AK-21 | `test_ak21_list_usable_without_bring`, `test_ak21_bring_offline_changes_nothing` | automatisch, plus Gerät |
| AK-22 | 10 Testfotos | Gerät, kostet KI-Budget |
| AK-23 | `test_ak23_text_import_ends_in_preview`, Playwright „Text aus Diktat …“ | automatisch mit KI-Attrappe, plus Gerät |
| AK-24 | `delikatessen ki-pruefen` | Erfüllt am 12.11.2026 mit der echten API |
| AK-25 | `test_ak25_budget_exhausted`, lokaler Test gegen LiteLLM (HTTP 422) | automatisch, plus Gerät |
| AK-26 | `test_ak26_thursday_run_creates_draft_and_notifies` | automatisch, plus Gerät |
| AK-27 | `test_ak27_journal_finds_all_dates`, `test_ak27_past_week_readonly_but_rateable` | automatisch, plus Gerät |

Für AK-06 lohnt es sich, zehn echte Rezeptseiten, die die Familie nutzt, als HTML unter `backend/tests/fixtures/rezeptseiten/` abzulegen. Wegen der Urheberrechte bleiben sie besser außerhalb des öffentlichen Repositorys oder werden auf das Schema-Markup gekürzt.

## 8. Stufe 2: Bring!

Die Einkaufsliste geht nur auf Knopfdruck an Bring!. Fällt Bring! aus, bleibt die Liste in der App vollständig nutzbar (AK-21).

1. Ein eigenes Bring!-Konto für die App anlegen und die Familienliste in der Bring!-App mit diesem Konto teilen. So sieht man in Bring!, was die App eingetragen hat, und das Familienpasswort bleibt aus dem Spiel.
2. In der App unter „Mehr“ › „Einstellungen“ › „Bring!“ E-Mail und Passwort dieses Kontos eintragen. Die App meldet sich zur Probe an, speichert das Passwort verschlüsselt und bietet die Listen zur Auswahl an.

Den Schlüssel für die Verschlüsselung (`DELIKATESSEN_SECRET_KEY`) legt `install.sh` bzw. `update.sh` beim ersten Lauf mit Stufe 2 in `/etc/delikatessen/env` an. Geht er verloren, muss das Bring!-Passwort neu eingegeben werden, sonst nichts.

`bring-api` ist eine inoffizielle Bibliothek und exakt auf eine Version festgelegt. Meldet die App „vermutlich hat sich die Schnittstelle geändert“, Bring! in den Einstellungen abschalten und auf ein Update warten.

## 9. Stufe 2: KI-Gateway

Fotos, Texte, Diktate und Seiten ohne Rezeptdaten liest die KI. Alle Anfragen laufen über ein eigenes Gateway (LiteLLM), das den Anthropic-Schlüssel hält und ein Monatsbudget erzwingt. Die App bekommt nur einen virtuellen Schlüssel mit Budget.

**Container anlegen:** Debian 12 oder 13, 1 vCPU, 4 GB RAM, 20 GB, unprivilegiert mit den Optionen `nesting` und `keyctl` für Docker (Proxmox: Optionen › Features). Firewall: eingehend nur Port 4000 vom delikatessen-LXC, ausgehend nur HTTPS.

**Docker installieren:** Debian bringt `docker compose` (Compose v2) nicht mit, Debian 12 hat nur das veraltete `docker-compose` 1.29. Docker und das Compose-Plugin kommen deshalb aus der Paketquelle von Docker:

```bash
apt update && apt install -y ca-certificates curl git openssl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt update && apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
docker compose version    # muss v2 oder neuer melden
```

**Gateway starten:**

```bash
git clone https://github.com/kallelix/Delikatessen.git /opt/delikatessen-src
cd /opt/delikatessen-src/deploy/ki-gateway
cp env.example .env && chmod 600 .env    # Schlüssel eintragen, siehe Kommentare
docker compose up -d
docker compose ps                        # beide Dienste "Up", db zusätzlich "(healthy)"
curl -s http://localhost:4000/health/liveliness   # nach etwa einer Minute: "I'm alive!"
```

**Schlüssel für die App mit Budget anlegen** (Beispiel 5 US-Dollar je 30 Tage), im Verzeichnis `ki-gateway`:

```bash
export $(grep ^LITELLM_MASTER_KEY= .env)
curl -s -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"models":["rezept-extraktion"],"max_budget":5,"budget_duration":"30d","key_alias":"delikatessen"}'
```

Den Wert von `key` im delikatessen-LXC in `/etc/delikatessen/env` als `DELIKATESSEN_KI_API_KEY` eintragen, dazu `DELIKATESSEN_KI_BASE_URL=http://<Adresse des Gateways>:4000`, dann `sudo systemctl restart delikatessen`.

**AK-24 prüfen**, bevor die Familie die KI nutzt:

```bash
sudo systemd-run --pipe --wait -p User=delikatessen -p EnvironmentFile=/etc/delikatessen/env \
  /opt/delikatessen/current/venv/bin/delikatessen ki-pruefen
```

Der Befehl schickt ein kurzes Beispielrezept durch das Gateway und meldet „AK-24 erfüllt“, wenn die Antwort im festgelegten Schema ankommt. Mit LiteLLM v1.108.5 und der echten API am 12.11.2026 erfüllt (ein Aufruf etwa 1,5 Cent). Die Kosten bucht das Gateway mit etwa einer Minute Verzögerung, direkt nach dem ersten Aufruf zeigt `ki-pruefen` deshalb noch „Budget: 0.00“. Scheitert die Prüfung nach einem Update von Gateway oder Modell, in `/etc/delikatessen/env` `DELIKATESSEN_KI_STRUCTURED=none` setzen. Dann steht das Schema im Prompt, und die App prüft jede Antwort selbst.

| Thema | Festlegung |
| --- | --- |
| Modell | Alias `rezept-extraktion` in `litellm-config.yaml`, Vorgabe `claude-opus-5-5`. Wechsel nur dort, danach `docker compose restart litellm` und `ki-pruefen` |
| Budget | Hängt am Schlüssel der App. Ändern nur im Gateway mit dem Master-Key. Ist es aufgebraucht, zeigt die App einen Hinweis, alles ohne KI läuft weiter (AK-25) |
| Datenschutz | An die KI gehen nur Rezepttext und Fotos, ohne EXIF und verkleinert (N-11). Das Gateway speichert keine Prompts (`turn_off_message_logging`) |
| Updates | Images sind auf Version und Digest festgelegt. Ein Update ist eine bewusste Änderung an `docker-compose.yml`, nie automatisch |
| Kosten | Unter „Mehr“ › „Status der Dienste“ zeigt die App den Verbrauch des Monats |

## 10. Stufe 2: Donnerstagslauf und Benachrichtigungen

Donnerstags zur Uhrzeit aus den Einstellungen (Vorgabe 18:00) entsteht ein Entwurf für die Woche ab dem nächsten Samstag, falls dort noch kein Platz belegt ist. Alle angemeldeten Geräte bekommen dann eine Benachrichtigung ohne Rezeptdetails (F-24). War der Dienst zur Uhrzeit aus, holt der nächste Start den Lauf bis Freitagabend nach.

- **Geräte anmelden:** in der App unter „Mehr“ › „Benachrichtigungen“. Das geht nur in der installierten App über HTTPS. Mit „Testnachricht schicken“ lässt es sich gleich prüfen.
- **Ausprobieren:** „Mehr“ › „Einstellungen“ › „Jetzt ausprobieren“ führt den Lauf sofort aus. Gibt es für nächste Woche schon einen Plan, bleibt er unverändert.
- **Netz:** Die App braucht ausgehend HTTPS zum Push-Dienst des Browsers (bei Chrome Firebase Cloud Messaging). Das Öffnen der Nachricht braucht wie immer das VPN.
- **Schlüssel:** Den VAPID-Schlüssel erzeugt die App selbst als `/var/lib/delikatessen/vapid_private.pem`. Er ist Teil der täglichen Sicherung. Geht er verloren, müssen sich die Geräte neu anmelden.
- **Absender:** `DELIKATESSEN_PUSH_CONTACT` in `/etc/delikatessen/env` auf eine echte Adresse setzen, etwa `mailto:familie@example.org`. Darüber kann sich ein Push-Dienst bei Problemen melden.

## 11. Planung in Stufe 2

Zwei Terme ergänzen die Formel aus Pflichtenheft Abschnitt 6, beide mit Gewicht in den Einstellungen:

| Größe | Bedeutung | Berechnung | Gewicht (Vorgabe) |
| --- | --- | --- | --- |
| V | Vorrat verbrauchen | Anteil der noch nicht abgedeckten Zutaten aus „diese Woche verbrauchen“, die das Rezept enthält. Ist eine Zutat einmal im Plan, zählt sie nicht mehr | 0,30 |
| N | Neues ausprobieren | 1 für ein noch nie gekochtes Rezept, sonst 0 | 0,10 |

„Diese Woche verbrauchen“ setzt man über „Rezepte“ › „Nach Zutaten suchen“. Die Auswahl hängt an der Woche und wirkt beim nächsten Erzeugen und bei „Neuer Vorschlag“. Der Grund am Platz lautet dann etwa „verbraucht Zucchini“.

Ganz vergangene Wochen sind nur lesbar (D-JOUR). Wertungen und „nicht gekocht“ lassen sich dort weiter nachtragen. Das Journal unter „Mehr“ listet alle Kochtermine und entfallenen Essen.

## 12. Abnahme Stufe 2 auf dem Gerät

- [ ] Bring!: Einkaufsliste senden, in der Bring!-App erscheinen alle Einträge mit Menge. Erneut senden erzeugt keine Dubletten (AK-20)
- [ ] Bring! in den Einstellungen abschalten, die Einkaufsliste bleibt vollständig nutzbar (AK-21)
- [x] `delikatessen ki-pruefen` meldet „AK-24 erfüllt“ (AK-24)
- [ ] 10 Testfotos, davon 3 handschriftlich: mindestens 8 nach höchstens drei Korrekturen speicherbar (AK-22)
- [ ] Rezept per Diktierknopf und per Mikrofon der Tastatur eingeben, beide ergeben eine Vorschau (AK-23)
- [ ] Budget im Gateway kurz auf 0 setzen: die App zeigt den Hinweis, Link-Import und Plan gehen weiter (AK-25)
- [ ] Benachrichtigungen auf jedem Familiengerät einschalten, „Jetzt ausprobieren“ bringt die Nachricht auf alle Geräte (AK-26)
- [ ] Im Journal ein Rezept suchen, alle Termine erscheinen. Eine vergangene Woche öffnen und eine Wertung nachtragen (AK-27)
