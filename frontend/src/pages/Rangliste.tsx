import { Link } from "react-router";
import { api } from "../api";
import { dayLabel, useLoad } from "../lib";
import type { Badge, Rankings } from "../types";

/** Lieblingsessen aus Bewertungen und Häufigkeit (F-12). Gerichte gewinnen, nicht Personen. */
export function Rangliste() {
  const data = useLoad(() => api.rankings(), [], true);
  const cooked = data.data?.ranking.filter((e) => e.cooked_count > 0) ?? [];
  const never = data.data?.ranking.filter((e) => e.cooked_count === 0) ?? [];
  return (
    <section className="page">
      <h1>Rangliste</h1>
      {data.error && <p className="error">{data.error}</p>}
      {data.data?.essen_des_monats && <MonthCard dish={data.data.essen_des_monats} />}
      {data.data && cooked.length === 0 && <p className="empty">Nach den ersten Bewertungen entsteht hier die Rangliste.</p>}
      <ol className="ranking">
        {cooked.map((e) => (
          <li key={e.recipe.id}>
            <Link to={`/rezepte/${e.recipe.id}`} className="row-btn">
              <span>{e.recipe.title}</span>
              <span className="muted small">
                {Math.round(e.favorite_score * 100)} Punkte · {e.cooked_count}× gekocht
                {e.last_cooked && ` · zuletzt ${dayLabel(e.last_cooked)}`}
              </span>
            </Link>
          </li>
        ))}
      </ol>
      {data.data && data.data.neu_ausprobiert.length > 0 && (
        <>
          <h2>Diesen Monat neu ausprobiert</h2>
          <ul className="plain">
            {data.data.neu_ausprobiert.map((n) => (
              <li key={n.recipe.id}>
                <Link to={`/rezepte/${n.recipe.id}`} className="row-btn">
                  <span>{n.recipe.title}</span>
                  <span className="muted small">{dayLabel(n.erstmals)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
      {data.data && data.data.abzeichen.length > 0 && <Badges badges={data.data.abzeichen} />}
      {never.length > 0 && (
        <details>
          <summary>Noch nie gekocht ({never.length})</summary>
          <ul className="plain">
            {never.map((e) => (
              <li key={e.recipe.id}>
                <Link to={`/rezepte/${e.recipe.id}`} className="row-btn">
                  {e.recipe.title}
                </Link>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function MonthCard({ dish }: { dish: NonNullable<Rankings["essen_des_monats"]> }) {
  const month = new Date(`${dish.monat}-15T12:00:00`).toLocaleDateString("de-DE", { month: "long" });
  return (
    <Link to={`/rezepte/${dish.recipe.id}`} className="card month-dish">
      {dish.recipe.image_url && <img src={dish.recipe.image_url} alt="" />}
      <span>
        <span className="muted small">Essen des Monats {month}{dish.laufend ? " (bisher)" : ""}</span>
        <strong>{dish.recipe.title}</strong>
        <span className="muted small">
          {Math.round(dish.mittel * 100)} Punkte aus {dish.wertungen} Wertungen
        </span>
      </span>
    </Link>
  );
}

/** Abzeichen der Familie für neu ausprobierte Gerichte (D-RANK), ohne Vergleich zwischen Personen. */
function Badges({ badges }: { badges: Badge[] }) {
  // erreichte Abzeichen und das nächste Ziel, der Rest bleibt eine Überraschung
  const next = badges.find((b) => !b.erreicht);
  const shown = [...badges.filter((b) => b.erreicht), ...(next ? [next] : [])];
  return (
    <>
      <h2>Abzeichen</h2>
      <ul className="plain badges">
        {shown.map((b) => (
          <li key={b.name} className={b.erreicht ? "badge-item done" : "badge-item"}>
            <strong>{b.name}</strong>
            <span className="muted small">{b.erreicht ? b.beschreibung : `${b.stand} von ${b.ziel} Gerichten ausprobiert`}</span>
            {!b.erreicht && (
              <span className="meter" aria-hidden="true">
                <span style={{ width: `${Math.round((b.stand / b.ziel) * 100)}%` }} />
              </span>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
