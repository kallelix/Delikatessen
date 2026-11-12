import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { pendingRecipeDeletes, useLoad } from "../lib";
import type { RecipeSummary } from "../types";

/** Suche und Filter (F-03). Filter stehen in der Adresse, damit "zurück" sie behält. */
export function Rezepte() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const tag = params.getAll("tag").map(Number);
  const size = params.get("size") ?? "";
  const maxDuration = params.get("max") ? Number(params.get("max")) : undefined;
  const favorite = params.get("fav") === "1";
  const [text, setText] = useState(q);
  const tags = useLoad(() => api.tags(), []);

  useEffect(() => {
    const t = window.setTimeout(() => {
      if (text !== q) update({ q: text || null });
    }, 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const list = useLoad(
    () => api.recipes({ q, tag, size: size || undefined, max_duration: maxDuration, favorite: favorite || undefined }),
    [params.toString()],
  );
  // Gerade gelöschte Rezepte bestehen auf dem Server noch, solange "Rückgängig" angeboten wird
  const recipes = list.data?.filter((r) => !pendingRecipeDeletes.has(r.id));

  function update(changes: Record<string, string | string[] | null>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      next.delete(k);
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x));
      else if (v) next.set(k, v);
    }
    setParams(next, { replace: true });
  }

  const toggleTag = (id: number) =>
    update({ tag: (tag.includes(id) ? tag.filter((t) => t !== id) : [...tag, id]).map(String) });

  return (
    <section className="page">
      <div className="page-head">
        <h1>Rezepte</h1>
        <Link className="link-btn" to="/rezepte/zutaten">
          Nach Zutaten suchen
        </Link>
      </div>
      <div className="search">
        <Icon name="suche" />
        <input
          type="search"
          placeholder="Titel oder Zutat"
          aria-label="Rezepte durchsuchen"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <div className="chips" role="group" aria-label="Filter">
        <button type="button" className="chip" aria-pressed={favorite} onClick={() => update({ fav: favorite ? null : "1" })}>
          <Icon name="stern" size={16} filled={favorite} /> Favoriten
        </button>
        <button type="button" className="chip" aria-pressed={size === "haupt"} onClick={() => update({ size: size === "haupt" ? null : "haupt" })}>
          Hauptmahlzeit
        </button>
        <button type="button" className="chip" aria-pressed={size === "klein"} onClick={() => update({ size: size === "klein" ? null : "klein" })}>
          Klein
        </button>
        <button type="button" className="chip" aria-pressed={maxDuration === 30} onClick={() => update({ max: maxDuration === 30 ? null : "30" })}>
          bis 30 Min.
        </button>
        {tags.data?.map((t) => (
          <button key={t.id} type="button" className="chip" aria-pressed={tag.includes(t.id)} onClick={() => toggleTag(t.id)}>
            {t.name}
          </button>
        ))}
      </div>

      {list.error && <p className="error">{list.error}</p>}
      {recipes && recipes.length === 0 && (
        <div className="empty">
          {q || tag.length || size || maxDuration || favorite ? (
            <p>Nichts gefunden.</p>
          ) : (
            <>
              <p>Noch keine Rezepte.</p>
              <Link className="btn primary" to="/neu">
                Erstes Rezept anlegen
              </Link>
            </>
          )}
        </div>
      )}
      <ul className="recipe-list">{recipes?.map((r) => <RecipeCard key={r.id} r={r} />)}</ul>
    </section>
  );
}

export function RecipeCard({ r }: { r: RecipeSummary }) {
  return (
    <li>
      <Link to={`/rezepte/${r.id}`} className={`recipe-card${r.excluded ? " excluded" : ""}`}>
        {r.image_url ? <img className="thumb" src={r.image_url} alt="" loading="lazy" /> : <span className="thumb placeholder" aria-hidden="true" />}
        <span className="recipe-card-body">
          <span className="recipe-card-title">
            {r.favorite && <Icon name="stern" size={16} filled />} {r.title}
          </span>
          <span className="muted small">
            {r.size === "haupt" ? "Hauptmahlzeit" : "klein"}
            {r.duration_min ? ` · ${r.duration_min} Min.` : ""}
            {r.tags.length > 0 && ` · ${r.tags.map((t) => t.name).join(", ")}`}
          </span>
          {!r.plannable && <span className="badge warn">Zutaten zuordnen</span>}
          {r.excluded && <span className="badge">nicht planen</span>}
        </span>
      </Link>
    </li>
  );
}
