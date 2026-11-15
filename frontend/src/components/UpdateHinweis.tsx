import { useEffect, useState } from "react";
import { api } from "../api";
import { errorText } from "../lib";
import type { UpdateStatus } from "../types";

const POLL_MS = 3000;
const CHECK_POLL_MS = 1500;

/** Nach dem Update: neuen Service Worker holen und die App frisch laden */
async function reloadApp() {
  try {
    const reg = await navigator.serviceWorker?.getRegistration();
    await reg?.update();
  } catch {
    // ohne Service Worker reicht das Neuladen
  }
  window.location.reload();
}

function dateText(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const day = d.toLocaleDateString("de-DE", { day: "numeric", month: "numeric" });
  return `${day} um ${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`;
}

/**
 * Update-Hinweis unter "Status der Dienste" und für Erwachsene der Knopf "Jetzt aktualisieren".
 * Den Rest erledigt der Server (delikatessen-update.path), die App wartet nur, bis die neue Version antwortet.
 */
export function UpdateHinweis({ initial, isAdult }: { initial: UpdateStatus; isAdult: boolean }) {
  const [u, setU] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const startVersion = initial.version;

  const [checkedBefore, setCheckedBefore] = useState<string | null | undefined>(undefined);

  useEffect(() => setU(initial), [initial]);

  // „Jetzt prüfen“: der Host fragt GitHub, das dauert meist nur Sekunden
  useEffect(() => {
    if (!u.prueft) return;
    const t = window.setInterval(async () => {
      try {
        const s = await api.status();
        if (s.update && !s.update.prueft) {
          setU(s.update);
          if (s.update.geprueft === checkedBefore) setError("Prüfen hat nicht geklappt. Später noch einmal versuchen.");
          setCheckedBefore(undefined);
        }
      } catch {
        // kurz keine Verbindung, weiter fragen
      }
    }, CHECK_POLL_MS);
    return () => window.clearInterval(t);
  }, [u.prueft, checkedBefore]);

  async function check() {
    setBusy(true);
    setError(null);
    setCheckedBefore(u.geprueft);
    try {
      setU(await api.checkUpdate());
    } catch (e) {
      setError(errorText(e));
      setCheckedBefore(undefined);
    } finally {
      setBusy(false);
    }
  }

  // Während des Updates ist der Server kurz weg: weiter fragen, bis die neue Version antwortet
  useEffect(() => {
    if (!u.laeuft) return;
    const t = window.setInterval(async () => {
      try {
        const s = await api.status();
        if (s.version !== startVersion) return void reloadApp();
        if (s.update) setU(s.update);
      } catch {
        // Neustart läuft
      }
    }, POLL_MS);
    return () => window.clearInterval(t);
  }, [u.laeuft, startVersion]);

  async function start() {
    if (!window.confirm(`Auf Version ${u.neueste} aktualisieren? Die App ist dabei etwa eine Minute nicht erreichbar.`)) return;
    setBusy(true);
    setError(null);
    try {
      setU(await api.startUpdate());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const failed = u.letztes?.status === "fehler" && !u.laeuft ? u.letztes : null;
  return (
    <>
      {u.laeuft ? (
        <li role="status">
          Update auf {u.neueste ?? "die neue Version"} läuft. Die App lädt sich danach von selbst neu.
        </li>
      ) : u.verfuegbar ? (
        <li>
          Version {u.neueste} ist verfügbar
          {u.url && (
            <>
              {" "}
              (
              <a href={u.url} target="_blank" rel="noreferrer">
                Was ist neu
              </a>
              )
            </>
          )}
          {isAdult && u.knopf && (
            <div>
              <button type="button" className="btn primary" disabled={busy} onClick={start}>
                Jetzt aktualisieren
              </button>
            </div>
          )}
        </li>
      ) : u.prueft ? (
        <li role="status" className="muted">
          Suche nach einer neuen Version …
        </li>
      ) : (
        (u.neueste || isAdult) && (
          <li className="muted">
            {u.neueste ? `Auf dem neuesten Stand${u.geprueft ? `, geprüft am ${dateText(u.geprueft)}` : ""}` : "Noch nicht nach Updates geschaut"}
            {isAdult && (
              <>
                {" "}
                <button type="button" className="link-btn" disabled={busy} onClick={check}>
                  Jetzt prüfen
                </button>
              </>
            )}
          </li>
        )
      )}
      {failed && (
        <li className="error" role="alert">
          {failed.meldung}
        </li>
      )}
      {error && (
        <li className="error" role="alert">
          {error}
        </li>
      )}
    </>
  );
}
