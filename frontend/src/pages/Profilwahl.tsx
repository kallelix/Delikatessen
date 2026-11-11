import { useState } from "react";
import { api } from "../api";
import { useApp } from "../AppContext";
import { errorText } from "../lib";

/** Beim ersten Öffnen wird ein Profil gewählt und im Gerät gespeichert (N-09). */
export function Profilwahl() {
  const { persons, chooseProfile, refreshPersons } = useApp();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function createFirst(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      const p = await api.createPerson({
        name: name.trim(),
        kind: "erwachsen",
        portion_factor: 1,
        active: true,
        netbird_ip: null,
        nogos: [],
      });
      chooseProfile(p.id);
      await refreshPersons();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (persons.length === 0) {
    return (
      <div className="welcome">
        <img src="/icon-192.png" alt="" width={72} height={72} />
        <h1>Willkommen bei Delikatessen</h1>
        <p>Zuerst eine erwachsene Person anlegen. Weitere Familienmitglieder kommen danach unter „Mehr“ dazu.</p>
        <form onSubmit={createFirst} className="stack">
          <label className="field">
            <span>Dein Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus required maxLength={80} />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="btn primary" disabled={busy || !name.trim()}>
            Loslegen
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="welcome">
      <img src="/icon-192.png" alt="" width={72} height={72} />
      <h1>Wer bist du?</h1>
      <p>Das Gerät merkt sich die Wahl. Wechseln geht jederzeit unter „Mehr“.</p>
      <div className="profile-grid">
        {persons.map((p) => (
          <button key={p.id} type="button" className="profile-btn" onClick={() => chooseProfile(p.id)}>
            <span className="avatar" aria-hidden="true">
              {p.name.slice(0, 1).toUpperCase()}
            </span>
            {p.name}
          </button>
        ))}
      </div>
    </div>
  );
}
