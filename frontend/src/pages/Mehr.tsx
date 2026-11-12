import { Link } from "react-router";
import { api } from "../api";
import { useApp } from "../AppContext";
import { useLoad } from "../lib";

export function Mehr() {
  const { persons, me, isAdult, chooseProfile } = useApp();
  const status = useLoad(() => api.status(), []);
  return (
    <section className="page">
      <h1>Mehr</h1>
      <ul className="plain menu">
        <li>
          <Link className="row-btn" to="/mehr/rangliste">
            Rangliste
          </Link>
        </li>
        {isAdult && (
          <>
            <li>
              <Link className="row-btn" to="/mehr/familie">
                Familie
              </Link>
            </li>
            <li>
              <Link className="row-btn" to="/mehr/einstellungen">
                Einstellungen
              </Link>
            </li>
            <li>
              <a className="row-btn" href="/api/v1/export/recipes" download>
                Alle Rezepte exportieren (JSON)
              </a>
            </li>
          </>
        )}
      </ul>

      <h2>Profil</h2>
      <p className="muted small">Angemeldet als {me?.name ?? "–"}. Das Gerät merkt sich die Wahl.</p>
      <div className="profile-grid">
        {persons.map((p) => (
          <button key={p.id} type="button" className="profile-btn" aria-pressed={p.id === me?.id} onClick={() => chooseProfile(p.id)}>
            <span className="avatar" aria-hidden="true">
              {p.name.slice(0, 1).toUpperCase()}
            </span>
            {p.name}
          </button>
        ))}
      </div>

      <h2>Status der Dienste</h2>
      {status.data ? (
        <ul className="plain status">
          <li>
            Version {status.data.version}, Datenbank {status.data.datenbank}
          </li>
          {Object.entries(status.data.dienste).map(([name, s]) => (
            <li key={name}>
              {name === "bring" ? "Bring!" : name === "ki" ? "KI" : "Benachrichtigungen"}: {s.aktiv ? `aktiv${s.hinweis ? `, ${s.hinweis}` : ""}` : s.hinweis}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{status.error ?? "…"}</p>
      )}
    </section>
  );
}
