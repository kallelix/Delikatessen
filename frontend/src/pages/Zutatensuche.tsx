import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { IngredientPicker } from "../components/IngredientPicker";
import { useToast } from "../components/Toast";
import { dayLabel, defaultPlanWeek, errorText } from "../lib";
import type { Ingredient, IngredientHit } from "../types";

const MAX = 30;

/** Was haben wir da? Rezepte nach dem Anteil abgedeckter Zutaten (D-ZUT), Übergabe an den Plan. */
export function Zutatensuche() {
  const [chosen, setChosen] = useState<Ingredient[]>([]);
  const [hits, setHits] = useState<IngredientHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();
  const week = defaultPlanWeek();

  useEffect(() => {
    if (chosen.length === 0) {
      setHits(null);
      return;
    }
    let stale = false;
    api.byIngredients(chosen.map((c) => c.id)).then(
      (h) => !stale && setHits(h),
      (e) => !stale && toast.show(errorText(e), { error: true }),
    );
    return () => void (stale = true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosen]);

  function add(ing: Ingredient) {
    if (chosen.some((c) => c.id === ing.id)) return;
    if (chosen.length >= MAX) return toast.show(`Höchstens ${MAX} Zutaten`, { error: true });
    setChosen([...chosen, ing]);
  }

  async function useUp() {
    setBusy(true);
    try {
      const plan = await api.plan(week);
      if (plan.readonly) throw new Error("Diese Woche ist schon vorbei");
      await api.setUseUp(week, plan.version, chosen.map((c) => c.id));
      toast.show("Für den Plan vorgemerkt. Jetzt neu erzeugen oder einzelne Plätze neu vorschlagen.");
      navigate(`/?woche=${week}`);
    } catch (e) {
      toast.show(errorText(e), { error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <h1>Was haben wir da?</h1>
      <p className="muted small">Zutaten wählen, die weg müssen oder gerade da sind. Rezepte, die am meisten davon nutzen, stehen oben.</p>
      {/* key: nach jeder Wahl ein leeres Feld für die nächste Zutat */}
      <IngredientPicker key={chosen.length} value="" label="Zutat hinzufügen" placeholder="Zutat hinzufügen, etwa Zucchini" allowCreate={false} onPick={add} />
      {chosen.length > 0 && (
        <div className="chips" role="list" aria-label="Gewählte Zutaten">
          {chosen.map((c) => (
            <button
              key={c.id}
              type="button"
              role="listitem"
              className="chip on"
              aria-label={`${c.name} entfernen`}
              onClick={() => setChosen(chosen.filter((x) => x.id !== c.id))}
            >
              {c.name} <Icon name="x" size={14} />
            </button>
          ))}
        </div>
      )}

      {hits && hits.length === 0 && <p className="empty">Kein Rezept enthält diese Zutaten.</p>}
      {hits && hits.length > 0 && (
        <ul className="plain hit-list">
          {hits.map((h) => (
            <li key={h.recipe.id}>
              <Link className="row-btn" to={`/rezepte/${h.recipe.id}`}>
                <span>
                  {h.recipe.title}
                  <span className="muted small"> · mit {h.treffer.join(", ")}</span>
                </span>
                <span className="muted small">{h.fehlend === 0 ? "alles da" : `${h.fehlend} ${h.fehlend === 1 ? "fehlt" : "fehlen"}`}</span>
              </Link>
              <span className="meter" aria-hidden="true">
                <span style={{ width: `${Math.round(h.anteil * 100)}%` }} />
              </span>
            </li>
          ))}
        </ul>
      )}

      {chosen.length > 0 && (
        <div className="actions-bottom">
          <button type="button" className="btn primary wide" disabled={busy} onClick={useUp}>
            Ab {dayLabel(week)} verbrauchen
          </button>
        </div>
      )}
    </section>
  );
}
