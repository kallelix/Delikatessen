import { Link } from "react-router";
import { api } from "../api";
import { dayLabel, useLoad } from "../lib";

/** Lieblingsessen aus Bewertungen und Häufigkeit (F-12). Gerichte gewinnen, nicht Personen. */
export function Rangliste() {
  const data = useLoad(() => api.rankings(), [], true);
  const cooked = data.data?.ranking.filter((e) => e.cooked_count > 0) ?? [];
  const never = data.data?.ranking.filter((e) => e.cooked_count === 0) ?? [];
  return (
    <section className="page">
      <h1>Rangliste</h1>
      {data.error && <p className="error">{data.error}</p>}
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
