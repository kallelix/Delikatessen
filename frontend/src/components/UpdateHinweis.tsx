import { useEffect, useState } from "react";
import { api } from "../api";
import { errorText } from "../lib";
import type { UpdateStatus } from "../types";

const POLL_MS = 3000;

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
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("de-DE", { day: "numeric", month: "numeric" });
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

  useEffect(() => setU(initial), [initial]);

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
      ) : (
        u.neueste && <li className="muted">Auf dem neuesten Stand{u.geprueft ? `, geprüft am ${dateText(u.geprueft)}` : ""}</li>
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
