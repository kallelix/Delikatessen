import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../AppContext";
import { Sheet } from "../components/Sheet";
import { useToast } from "../components/Toast";
import { errorText, useLoad } from "../lib";
import type { Group, Ingredient, IngredientGap } from "../types";
import { COUNT_UNITS, FOOD_GROUPS, formatNumber, parseAmount, UNITS } from "../units";

const MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
const MONTHS_LONG = [
  "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember",
];

function gapText(g: IngredientGap): string {
  const parts = [g.recipes === 1 ? "in 1 Rezept" : `in ${g.recipes} Rezepten`];
  if (g.missing_units.length) parts.push(`Gewicht fehlt für ${g.missing_units.join(", ")}`);
  if (g.missing_group) parts.push("Gruppe fehlt");
  return parts.join(" · ");
}

/** Mehr › Zutaten pflegen: Gruppen, Gewichte, Dichte und Saison (Pflichtenheft Stufe 3, Abschnitt 8). */
export function ZutatenPflegen() {
  const { isAdult } = useApp();
  const gaps = useLoad(() => api.ingredientGaps(), []);
  const groups = useLoad(() => api.groups(), []);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Ingredient[] | null>(null);
  const [edit, setEdit] = useState<{ ing: Ingredient; missing: string[] } | null>(null);

  useEffect(() => {
    const text = q.trim();
    if (text.length < 2) {
      setHits(null);
      return;
    }
    let stale = false;
    const t = setTimeout(() => {
      api.ingredients(text).then((r) => !stale && setHits(r), () => !stale && setHits([]));
    }, 200);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [q]);

  if (!isAdult) return <p className="page notice">Zutaten pflegen nur Erwachsene.</p>;

  return (
    <section className="page">
      <h1>Zutaten pflegen</h1>
      <p className="muted small">
        Gewichte, Gruppen und Saison gelten sofort für alle Rezepte. Die Grundwerte bringt die App mit. Was ihr hier
        ändert, bleibt auch nach Updates stehen.
      </p>

      <label className="field">
        <span>Zutat suchen</span>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="z. B. Zwiebel" />
      </label>
      {hits && (
        <ul className="plain">
          {hits.length === 0 && <li className="muted">Nichts gefunden.</li>}
          {hits.map((i) => (
            <li key={i.id}>
              <button type="button" className="row-btn" onClick={() => setEdit({ ing: i, missing: [] })}>
                <span>{i.name}</span>
                <span className="muted small">{i.food_group ?? "Gruppe fehlt"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <h2>Offen{gaps.data ? ` (${gaps.data.length})` : ""}</h2>
      {gaps.error && <p className="error">{gaps.error}</p>}
      {gaps.data?.length === 0 && <p className="muted">Alles gepflegt. Jede Zutat hat eine Gruppe und jede Einheit ein Gewicht.</p>}
      <ul className="plain">
        {gaps.data?.map((g) => (
          <li key={g.ingredient.id}>
            <button type="button" className="row-btn" onClick={() => setEdit({ ing: g.ingredient, missing: g.missing_units })}>
              <span>{g.ingredient.name}</span>
              <span className="muted small">{gapText(g)}</span>
            </button>
          </li>
        ))}
      </ul>

      {edit && (
        <ZutatBearbeiten
          ing={edit.ing}
          missing={edit.missing}
          groups={groups.data ?? []}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            setHits(null);
            setQ("");
            void gaps.reload();
          }}
        />
      )}
    </section>
  );
}

type WeightRow = { unit: string; grams: string };

function ZutatBearbeiten({
  ing,
  missing,
  groups,
  onClose,
  onSaved,
}: {
  ing: Ingredient;
  missing: string[];
  groups: Group[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [groupId, setGroupId] = useState(ing.group_id);
  const [unit, setUnit] = useState(ing.default_unit);
  const [foodGroup, setFoodGroup] = useState(ing.food_group);
  const [density, setDensity] = useState(ing.density != null ? formatNumber(ing.density) : "");
  const [months, setMonths] = useState<number[]>(ing.season_months ?? []);
  const [aliases, setAliases] = useState(ing.aliases.join(", "));
  const [rows, setRows] = useState<WeightRow[]>(() => [
    ...Object.entries(ing.weights).map(([u, g]) => ({ unit: u, grams: formatNumber(g) })),
    ...missing.filter((u) => !(u in ing.weights)).map((u) => ({ unit: u, grams: "" })),
  ]);
  const [busy, setBusy] = useState(false);

  const setRow = (i: number, r: Partial<WeightRow>) => setRows(rows.map((x, j) => (j === i ? { ...x, ...r } : x)));
  const addRow = () => {
    const free = COUNT_UNITS.find((u) => !rows.some((r) => r.unit === u)) ?? "Stück";
    setRows([...rows, { unit: free, grams: "" }]);
  };
  const toggleMonth = (m: number) => setMonths(months.includes(m) ? months.filter((x) => x !== m) : [...months, m].sort((a, b) => a - b));

  async function save() {
    const weights: Record<string, number> = {};
    for (const r of rows) {
      if (!r.grams.trim()) continue;
      const g = parseAmount(r.grams);
      if (g === null || g <= 0) {
        toast.show(`Gewicht für ${r.unit} ist keine Zahl`, { error: true });
        return;
      }
      weights[r.unit] = g;
    }
    let d: number | null = null;
    if (density.trim()) {
      d = parseAmount(density);
      if (d === null || d <= 0) {
        toast.show("Dichte ist keine Zahl", { error: true });
        return;
      }
    }
    setBusy(true);
    try {
      await api.updateIngredient(ing.id, {
        group_id: groupId,
        default_unit: unit,
        food_group: foodGroup,
        density: d,
        season_months: months.length ? months : null,
        weights,
        aliases: aliases
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
      });
      toast.show(`${ing.name} gespeichert`);
      onSaved();
    } catch (e) {
      toast.show(errorText(e), { error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet title={ing.name} onClose={onClose}>
      <div className="stack">
        <div className="row2">
          <label className="field">
            <span>Gruppe</span>
            <select value={foodGroup ?? ""} onChange={(e) => setFoodGroup(e.target.value || null)}>
              <option value="">– fehlt –</option>
              {FOOD_GROUPS.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Kategorie</span>
            <select value={groupId ?? ""} onChange={(e) => setGroupId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">–</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="field">
          <legend>Gewicht je Einheit</legend>
          {rows.length === 0 && <p className="muted small">Noch keine. Für g und ml braucht es keins.</p>}
          {rows.map((r, i) => (
            <div key={i} className="weight-row">
              <select aria-label="Einheit" value={r.unit} onChange={(e) => setRow(i, { unit: e.target.value })}>
                {COUNT_UNITS.map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </select>
              <input
                aria-label={`Gramm je ${r.unit}`}
                inputMode="decimal"
                placeholder="Gramm"
                value={r.grams}
                onChange={(e) => setRow(i, { grams: e.target.value })}
              />
              <span>g</span>
              <button type="button" className="link-btn" aria-label={`${r.unit} entfernen`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                ✕
              </button>
            </div>
          ))}
          <button type="button" className="link-btn" onClick={addRow}>
            + Einheit
          </button>
        </fieldset>

        <div className="row2">
          <label className="field">
            <span>Standard-Einheit</span>
            <select value={unit ?? ""} onChange={(e) => setUnit(e.target.value || null)}>
              <option value="">–</option>
              {UNITS.map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Dichte g/ml</span>
            <input inputMode="decimal" placeholder="1" value={density} onChange={(e) => setDensity(e.target.value)} />
          </label>
        </div>

        <fieldset className="field">
          <legend>Saison</legend>
          <p className="muted small">Monate mit Ernte aus der Region. Keine Auswahl heißt ganzjährig. Saison gibt beim Planen nur einen Bonus.</p>
          <div className="chips months">
            {MONTHS.map((m, i) => (
              <button key={m} type="button" className="chip" aria-label={MONTHS_LONG[i]} aria-pressed={months.includes(i + 1)} onClick={() => toggleMonth(i + 1)}>
                {m}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="field">
          <span>Weitere Namen</span>
          <input value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="durch Komma getrennt" />
        </label>

        <div className="row2">
          <button type="button" className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button type="button" className="btn primary" onClick={save} disabled={busy}>
            Speichern
          </button>
        </div>
      </div>
    </Sheet>
  );
}
