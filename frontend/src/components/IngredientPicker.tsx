import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import type { Ingredient } from "../types";

/**
 * Auswahl aus dem Zutatenkatalog mit Autovervollständigung über Namen und Aliasse.
 * Unbekanntes lässt sich mit einem Tipp neu anlegen (Abschnitt 4).
 */
export function IngredientPicker({
  value,
  onPick,
  placeholder = "Zutat suchen",
  label,
  autoFocus,
}: {
  value: string;
  onPick: (ing: Ingredient) => void;
  placeholder?: string;
  label: string;
  autoFocus?: boolean;
}) {
  const [q, setQ] = useState(value);
  const [hits, setHits] = useState<Ingredient[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const listId = useId();
  const seq = useRef(0);

  useEffect(() => setQ(value), [value]);

  useEffect(() => {
    if (!open || !q.trim()) {
      setHits([]);
      return;
    }
    const n = ++seq.current;
    const t = window.setTimeout(async () => {
      try {
        const res = await api.ingredients(q.trim());
        if (n === seq.current) setHits(res.slice(0, 8));
      } catch {
        // ohne Netz keine Vorschläge
      }
    }, 150);
    return () => window.clearTimeout(t);
  }, [q, open]);

  const exact = hits.some((h) => h.name.toLowerCase() === q.trim().toLowerCase());

  async function create() {
    setBusy(true);
    try {
      const ing = await api.createIngredient(q.trim());
      onPick(ing);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="picker">
      <input
        type="search"
        value={q}
        aria-label={label}
        placeholder={placeholder}
        autoFocus={autoFocus}
        role="combobox"
        aria-expanded={open && (hits.length > 0 || !!q.trim())}
        aria-controls={listId}
        aria-autocomplete="list"
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {open && q.trim() && (
        <ul className="picker-list" id={listId} role="listbox">
          {hits.map((h) => (
            <li key={h.id} role="option" aria-selected="false">
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onPick(h);
                  setOpen(false);
                }}
              >
                {h.name}
                {h.group && <span className="muted"> · {h.group}</span>}
              </button>
            </li>
          ))}
          {!exact && (
            <li role="option" aria-selected="false">
              <button type="button" disabled={busy} onMouseDown={(e) => e.preventDefault()} onClick={create}>
                „{q.trim()}“ neu im Katalog anlegen
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
