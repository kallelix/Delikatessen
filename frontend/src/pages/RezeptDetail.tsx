import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";
import { dateLabel, errorText, useLoad } from "../lib";
import { formatQuantity, scale } from "../units";
import type { Recipe } from "../types";

export function RezeptDetail() {
  const id = Number(useParams().id);
  const recipe = useLoad(() => api.recipe(id), [id]);
  const navigate = useNavigate();
  const toast = useToast();
  const [servings, setServings] = useState<number | null>(null);
  const [hidden, setHidden] = useState(false);

  if (recipe.error && !recipe.data) return <p className="error page">{recipe.error}</p>;
  if (!recipe.data || hidden) return <div className="page" aria-busy="true" />;
  const r = recipe.data;
  const portions = servings ?? r.servings;

  async function toggle(field: "favorite" | "excluded") {
    try {
      const s = await api.patchRecipe(r.id, { [field]: !r[field] });
      recipe.setData({ ...r, favorite: s.favorite, excluded: s.excluded });
    } catch (e) {
      toast.show(errorText(e), { error: true });
    }
  }

  function remove() {
    // Löschen lässt sich kurz rückgängig machen (Abschnitt 9)
    setHidden(true);
    navigate("/rezepte");
    toast.undoable(
      `„${r.title}“ gelöscht`,
      async () => {
        try {
          await api.deleteRecipe(r.id);
        } catch (e) {
          toast.show(errorText(e), { error: true });
        }
      },
      () => navigate(`/rezepte/${r.id}`),
    );
  }

  return (
    <article className="page recipe">
      {r.image_url && <img className="hero" src={r.image_url} alt="" />}
      <div className="recipe-head">
        <h1>{r.title}</h1>
        <button
          type="button"
          className={`icon-btn star${r.favorite ? " on" : ""}`}
          aria-pressed={r.favorite}
          aria-label="Favorit"
          onClick={() => toggle("favorite")}
        >
          <Icon name="stern" filled={r.favorite} />
        </button>
      </div>
      <p className="muted">
        {r.size === "haupt" ? "Hauptmahlzeit" : "Kleine Mahlzeit"}
        {r.duration_min ? ` · ${r.duration_min} Minuten` : ""}
        {r.tags.length > 0 && ` · ${r.tags.map((t) => t.name).join(", ")}`}
      </p>
      {!r.plannable && (
        <p className="notice">
          Noch nicht planbar: Nicht jede Zutat ist dem Katalog zugeordnet.{" "}
          <Link to={`/rezepte/${r.id}/bearbeiten`}>Jetzt zuordnen</Link>
        </p>
      )}
      {r.excluded && <p className="notice">Von der Planung ausgeschlossen.</p>}

      <div className="portions">
        <span>Portionen</span>
        <button type="button" className="icon-btn" aria-label="Weniger Portionen" onClick={() => setServings(Math.max(1, portions - 1))}>
          −
        </button>
        <output aria-live="polite">{portions}</output>
        <button type="button" className="icon-btn" aria-label="Mehr Portionen" onClick={() => setServings(Math.min(50, portions + 1))}>
          +
        </button>
      </div>

      <h2>Zutaten</h2>
      <IngredientList recipe={r} portions={portions} />

      {r.steps.length > 0 && (
        <>
          <h2>Zubereitung</h2>
          <ol className="steps">
            {r.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </>
      )}

      <p className="muted small">
        {r.cooked_count > 0
          ? `${r.cooked_count}-mal gekocht, zuletzt am ${dateLabel(r.last_cooked!)}.`
          : "Noch nie gekocht."}
        {r.source_url && (
          <>
            {" "}
            <a href={r.source_url} target="_blank" rel="noreferrer noopener">
              Quelle
            </a>
          </>
        )}
      </p>

      <div className="actions-inline">
        <Link className="btn" to={`/rezepte/${r.id}/bearbeiten`}>
          <Icon name="stift" /> Bearbeiten
        </Link>
        <button type="button" className="btn" onClick={() => toggle("excluded")}>
          {r.excluded ? "Wieder planen" : "Nicht planen"}
        </button>
        <button type="button" className="btn danger" onClick={remove}>
          <Icon name="loeschen" /> Löschen
        </button>
      </div>
      <div className="actions-bottom">
        <Link className="btn primary wide" to={`/rezepte/${r.id}/kochen?portionen=${portions}`}>
          Kochen starten
        </Link>
      </div>
    </article>
  );
}

export function IngredientList({ recipe, portions, large }: { recipe: Recipe; portions: number; large?: boolean }) {
  const factor = portions / recipe.servings;
  return (
    <ul className={`ingredients${large ? " large" : ""}`}>
      {recipe.ingredients.map((i, idx) => (
        <li key={idx}>
          <span className="qty">{formatQuantity(scale(i.amount, i.unit, factor), i.unit)}</span>
          <span>
            {i.name}
            {i.note && <span className="muted">, {i.note}</span>}
            {!i.ingredient_id && !large && <span className="badge warn">nicht zugeordnet</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}
