import { useState } from "react";
import { api } from "../api";
import { useApp } from "../AppContext";
import { Icon } from "../components/Icon";
import { IngredientPicker } from "../components/IngredientPicker";
import { Sheet } from "../components/Sheet";
import { useToast } from "../components/Toast";
import { errorText, useLoad } from "../lib";
import { formatNumber } from "../units";
import type { NoGo, Person } from "../types";

type Draft = Omit<Person, "id"> & { id?: number };

const NEW: Draft = { name: "", kind: "erwachsen", portion_factor: 1, active: true, netbird_ip: null, nogos: [] };

/** Familie pflegen: Personen, Art, Portionsfaktor, No-go-Zutaten (F-40). */
export function Familie() {
  const { persons, refreshPersons, isAdult, me, chooseProfile } = useApp();
  const [draft, setDraft] = useState<Draft | null>(null);
  const toast = useToast();

  if (!isAdult) return <p className="page notice">Die Familie pflegen nur Erwachsene.</p>;

  async function remove(p: Person) {
    if (!window.confirm(`${p.name} wirklich entfernen? Die Bewertungen dieser Person gehen verloren.`)) return;
    try {
      await api.deletePerson(p.id);
      if (p.id === me?.id) chooseProfile(null);
      await refreshPersons();
    } catch (e) {
      toast.show(errorText(e), { error: true });
    }
  }

  return (
    <section className="page">
      <h1>Familie</h1>
      <ul className="plain person-list">
        {persons.map((p) => (
          <li key={p.id} className={p.active ? "" : "inactive"}>
            <button type="button" className="row-btn" onClick={() => setDraft({ ...p })}>
              <span>
                {p.name} <span className="muted small">({p.kind === "kind" ? "Kind" : "Erwachsen"}, Portion {formatNumber(p.portion_factor)})</span>
              </span>
              <span className="muted small">
                {p.nogos.length ? `No-go: ${p.nogos.map((n) => n.name).join(", ")}` : "keine No-gos"}
                {!p.active && " · isst nicht mit"}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="btn primary wide" onClick={() => setDraft({ ...NEW })}>
        <Icon name="neu" /> Person hinzufügen
      </button>
      {draft && (
        <PersonSheet
          draft={draft}
          onClose={() => setDraft(null)}
          onSaved={async () => {
            setDraft(null);
            await refreshPersons();
          }}
          onDelete={draft.id ? () => remove(draft as Person).then(() => setDraft(null)) : undefined}
        />
      )}
    </section>
  );
}

function PersonSheet({
  draft: initial,
  onClose,
  onSaved,
  onDelete,
}: {
  draft: Draft;
  onClose: () => void;
  onSaved: () => Promise<void>;
  onDelete?: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const [factor, setFactor] = useState(formatNumber(initial.portion_factor));
  const [error, setError] = useState<string | null>(null);
  const groups = useLoad(() => api.groups(), []);
  const [pick, setPick] = useState("");

  function addNogo(n: NoGo) {
    const exists = d.nogos.some((x) => (n.ingredient_id && x.ingredient_id === n.ingredient_id) || (n.group_id && x.group_id === n.group_id));
    if (!exists) setD({ ...d, nogos: [...d.nogos, n] });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const pf = Number(factor.replace(",", "."));
    if (!d.name.trim()) return setError("Bitte einen Namen angeben.");
    if (!(pf > 0 && pf <= 5)) return setError("Der Portionsfaktor muss zwischen 0 und 5 liegen.");
    const body = {
      name: d.name.trim(),
      kind: d.kind,
      portion_factor: pf,
      active: d.active,
      netbird_ip: d.netbird_ip?.trim() || null,
      nogos: d.nogos.map((n) => ({ ingredient_id: n.ingredient_id ?? null, group_id: n.group_id ?? null })),
    };
    try {
      if (d.id) await api.updatePerson(d.id, body);
      else await api.createPerson(body);
      await onSaved();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Sheet title={d.id ? d.name : "Neue Person"} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label className="field">
          <span>Name</span>
          <input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} maxLength={80} />
        </label>
        <div className="seg" role="radiogroup" aria-label="Art">
          {(["erwachsen", "kind"] as const).map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={d.kind === k}
              onClick={() => {
                setD({ ...d, kind: k });
                if (!d.id) setFactor(k === "kind" ? "0,5" : "1");
              }}
            >
              {k === "kind" ? "Kind" : "Erwachsen"}
            </button>
          ))}
        </div>
        <label className="field">
          <span>Portionsfaktor (1 = ganze Portion)</span>
          <input inputMode="decimal" value={factor} onChange={(e) => setFactor(e.target.value)} />
        </label>
        <label className="check">
          <input type="checkbox" checked={d.active} onChange={(e) => setD({ ...d, active: e.target.checked })} />
          Isst mit (zählt für Planung und Einkauf)
        </label>

        <fieldset className="field">
          <legend>No-go-Zutaten</legend>
          <div className="chips">
            {d.nogos.map((n, i) => (
              <button key={i} type="button" className="chip on" aria-label={`${n.name} entfernen`}
                onClick={() => setD({ ...d, nogos: d.nogos.filter((_, j) => j !== i) })}>
                {n.name} <Icon name="x" size={14} />
              </button>
            ))}
            {d.nogos.length === 0 && <span className="muted small">keine</span>}
          </div>
          <IngredientPicker value={pick} label="No-go-Zutat hinzufügen" placeholder="Zutat hinzufügen"
            onPick={(ing) => {
              addNogo({ ingredient_id: ing.id, name: ing.name });
              setPick("");
            }}
          />
          <select aria-label="Ganze Gruppe als No-go" value="" onChange={(e) => {
              const g = groups.data?.find((x) => x.id === Number(e.target.value));
              if (g) addNogo({ group_id: g.id, name: `${g.name} (Gruppe)` });
            }}>
            <option value="">Ganze Gruppe ausschließen …</option>
            {groups.data?.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </fieldset>

        <label className="field">
          <span>NetBird-IP des Geräts (optional)</span>
          <input inputMode="decimal" placeholder="100.64.0.12" value={d.netbird_ip ?? ""} onChange={(e) => setD({ ...d, netbird_ip: e.target.value })} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary wide">Speichern</button>
        {onDelete && (
          <button type="button" className="btn danger wide" onClick={onDelete}>
            Person entfernen
          </button>
        )}
      </form>
    </Sheet>
  );
}
