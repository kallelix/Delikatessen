import { useEffect, useState } from "react";
import { api } from "../api";
import { errorText, useLoad } from "../lib";
import type { BringList } from "../types";
import { useToast } from "./Toast";

/** Bring!-Konto verbinden, Liste wählen, abschalten (Abschnitt 8). Wirkt sofort, ohne den Speichern-Knopf. */
export function BringEinstellungen() {
  const cfg = useLoad(() => api.bring(), []);
  const [lists, setLists] = useState<BringList[] | null>(null);
  const [mail, setMail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const c = cfg.data;

  useEffect(() => {
    // Listen zur Auswahl nur laden, wenn ein Konto verbunden ist
    if (c?.configured && lists === null) {
      api.bringLists().then(setLists, (e) => setError(errorText(e)));
    }
  }, [c?.configured, lists]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const connect = () =>
    run(async () => {
      setLists(await api.bringAccount(mail.trim(), password));
      setPassword("");
      await cfg.reload();
      toast.show("Mit Bring! verbunden");
    });

  const disconnect = () =>
    run(async () => {
      cfg.setData(await api.deleteBringAccount());
      setLists(null);
      setMail("");
    });

  const save = (enabled: boolean, list?: BringList) =>
    run(async () => {
      cfg.setData(await api.saveBring(enabled, list));
    });

  if (!c) return <p className="muted">{cfg.error ?? "…"}</p>;

  return (
    <div className="bring-settings">
      {c.secret_key_missing && (
        <p className="notice">
          Auf dem Server fehlt DELIKATESSEN_SECRET_KEY. Ohne ihn lassen sich keine Zugangsdaten speichern. Ein Update mit
          deploy/update.sh legt ihn an.
        </p>
      )}
      {!c.configured ? (
        <>
          <p className="muted small">
            Die App legt Einträge mit einem eigenen Bring!-Konto an. Am besten ein eigenes Konto für die App einrichten und
            die Familienliste damit teilen.
          </p>
          <label className="field">
            <span>E-Mail des Bring!-Kontos</span>
            <input type="email" autoComplete="off" value={mail} onChange={(e) => setMail(e.target.value)} />
          </label>
          <label className="field">
            <span>Passwort</span>
            <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button type="button" className="btn" disabled={busy || !mail.trim() || !password || c.secret_key_missing} onClick={connect}>
            {busy ? "Verbinde …" : "Mit Bring! verbinden"}
          </button>
        </>
      ) : (
        <>
          <label className="field check">
            <input type="checkbox" checked={c.enabled} disabled={busy} onChange={(e) => save(e.target.checked)} />
            <span>Bring! verwenden</span>
          </label>
          <label className="field">
            <span>Liste</span>
            <select
              value={c.list_uuid ?? ""}
              disabled={busy || !lists}
              onChange={(e) => {
                const l = lists?.find((x) => x.uuid === e.target.value);
                if (l) void save(c.enabled, l);
              }}
            >
              {!lists && <option value={c.list_uuid ?? ""}>{c.list_name ?? "…"}</option>}
              {lists?.map((l) => (
                <option key={l.uuid} value={l.uuid}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <p className="muted small">
            Verbunden als {c.mail}.{" "}
            <button type="button" className="link-btn" disabled={busy} onClick={disconnect}>
              Konto trennen
            </button>
          </p>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
