import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { dayLabel, errorText, MEAL_LABEL } from "../lib";
import type { HistoryEntry, HistoryFilter } from "../types";

const RATING_LABEL: Record<NonNullable<HistoryFilter["wertung"]>, string> = {
  lecker: "lecker",
  okay: "okay",
  mies: "mies",
  ohne: "noch ohne Wertung",
};

function stars(m: number | null): string {
  if (m === null) return "";
  return m >= 0.75 ? "lecker" : m >= 0.25 ? "okay" : "mies";
}

/** Journal: alle Kochereignisse und entfallenen Essen, durchsuchbar nach Rezept und Zutat (D-JOUR). */
export function Journal() {
  const [q, setQ] = useState("");
  const [von, setVon] = useState("");
  const [bis, setBis] = useState("");
  const [wertung, setWertung] = useState<HistoryFilter["wertung"] | "">("");
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    const t = window.setTimeout(() => {
      api
        .history({ q: q.trim() || undefined, von: von || undefined, bis: bis || undefined, wertung: wertung || undefined })
        .then(
          (e) => {
            if (!stale) {
              setEntries(e);
              setError(null);
            }
          },
          (e) => !stale && setError(errorText(e)),
        );
    }, 250);
    return () => {
      stale = true;
      window.clearTimeout(t);
    };
  }, [q, von, bis, wertung]);

  const byMonth = useMemo(() => {
    const map = new Map<string, HistoryEntry[]>();
    entries?.forEach((e) => {
      const key = new Date(`${e.date}T12:00:00`).toLocaleDateString("de-DE", { month: "long", year: "numeric" });
      map.set(key, [...(map.get(key) ?? []), e]);
    });
    return [...map.entries()];
  }, [entries]);

  const cooked = entries?.filter((e) => e.status === "gekocht").length ?? 0;

  return (
    <section className="page">
      <h1>Journal</h1>
      <input type="search" placeholder="Rezept oder Zutat suchen" aria-label="Journal durchsuchen" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="row2 filters">
        <label className="field">
          <span>Von</span>
          <input type="date" value={von} onChange={(e) => setVon(e.target.value)} />
        </label>
        <label className="field">
          <span>Bis</span>
          <input type="date" value={bis} onChange={(e) => setBis(e.target.value)} />
        </label>
      </div>
      <div className="chips" role="group" aria-label="Wertung">
        {(Object.keys(RATING_LABEL) as NonNullable<HistoryFilter["wertung"]>[]).map((w) => (
          <button key={w} type="button" className="chip" aria-pressed={wertung === w} onClick={() => setWertung(wertung === w ? "" : w)}>
            {RATING_LABEL[w]}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {entries && entries.length === 0 && <p className="empty">Nichts gefunden.</p>}
      {entries && entries.length > 0 && <p className="muted small">{cooked}-mal gekocht</p>}

      {byMonth.map(([month, list]) => (
        <section key={month} className="journal-month">
          <h2>{month}</h2>
          <ul className="plain">
            {list.map((e) => (
              <li key={e.slot_id} className={e.status === "entfallen" ? "journal-entry cancelled" : "journal-entry"}>
                <Link className="row-btn" to={`/?woche=${e.week_start}`}>
                  <span>
                    {e.status === "entfallen" ? "Essen entfiel" : (e.recipe?.title ?? "–")}
                    {e.status === "entfallen" && e.recipe && <span className="muted small"> · {e.recipe.title}</span>}
                  </span>
                  <span className="muted small">
                    {dayLabel(e.date)} {MEAL_LABEL[e.meal]}
                    {e.mittel !== null && ` · ${stars(e.mittel)}`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </section>
  );
}
