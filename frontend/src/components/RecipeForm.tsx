import { useEffect, useState } from "react";
import { api } from "../api";
import { errorText, useLoad } from "../lib";
import { formatNumber, parseAmount, UNITS } from "../units";
import type { RecipeIngredient, RecipeInput, Size } from "../types";
import { Icon } from "./Icon";
import { IngredientPicker } from "./IngredientPicker";

interface Row extends RecipeIngredient {
  key: number;
  amountText: string;
  catalogName: string | null;
  line?: string;
}

let rowKey = 0;
const toRow = (i: RecipeIngredient & { line?: string }): Row => ({
  ...i,
  key: ++rowKey,
  amountText: i.amount === null ? "" : formatNumber(i.amount),
  catalogName: i.ingredient_id ? (i.ingredient_name ?? i.name) : null,
});
const emptyRow = (): Row => toRow({ amount: null, unit: null, name: "", note: null, ingredient_id: null });

export const EMPTY_RECIPE: RecipeInput = {
  title: "",
  servings: 4,
  size: "haupt",
  duration_min: null,
  steps: [],
  tag_ids: [],
  ingredients: [],
  source_url: null,
  favorite: false,
  excluded: false,
};

/**
 * Rezeptformular (F-01): neu, bearbeiten und Importvorschau.
 * Offene Zutaten sind markiert und lassen sich direkt dem Katalog zuordnen.
 */
export function RecipeForm({
  initial,
  initialIngredients,
  remoteImage,
  currentImage,
  initialImage,
  submitLabel,
  onSubmit,
  onCancel,
  hint,
}: {
  initial: RecipeInput;
  initialIngredients?: (RecipeIngredient & { line?: string })[];
  remoteImage?: string | null;
  currentImage?: string | null;
  initialImage?: File | null;
  submitLabel: string;
  onSubmit: (data: RecipeInput, extras: { image: File | null; useRemoteImage: boolean; removeImage: boolean }) => Promise<void>;
  onCancel?: () => void;
  hint?: string;
}) {
  const [title, setTitle] = useState(initial.title);
  const [size, setSize] = useState<Size>(initial.size);
  const [servings, setServings] = useState(String(initial.servings));
  const [duration, setDuration] = useState(initial.duration_min ? String(initial.duration_min) : "");
  const [steps, setSteps] = useState(initial.steps.join("\n"));
  const [tagIds, setTagIds] = useState<number[]>(initial.tag_ids);
  const [rows, setRows] = useState<Row[]>(() => {
    const src = initialIngredients ?? initial.ingredients;
    return src.length ? src.map(toRow) : [emptyRow()];
  });
  const [sourceUrl, setSourceUrl] = useState(initial.source_url ?? "");
  const [image, setImage] = useState<File | null>(initialImage ?? null);
  const [useRemote, setUseRemote] = useState(!!remoteImage);
  const [removeImage, setRemoveImage] = useState(false);
  const fromPhoto = !!remoteImage?.startsWith("/api/");
  const [newTag, setNewTag] = useState("");
  const [picking, setPicking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function pick(input: HTMLInputElement) {
    const f = input.files?.[0];
    if (f) setImage(f);
    input.value = "";
  }
  const tags = useLoad(() => api.tags(), []);

  const open = rows.filter((r) => r.name.trim() && !r.ingredient_id).length;

  function setRow(key: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  async function addTag() {
    const name = newTag.trim();
    if (!name) return;
    try {
      const t = await api.createTag(name);
      await tags.reload();
      setTagIds((ids) => (ids.includes(t.id) ? ids : [...ids, t.id]));
      setNewTag("");
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const ingredients = rows
      .filter((r) => r.name.trim())
      .map((r) => ({
        amount: parseAmount(r.amountText),
        unit: r.unit || null,
        name: r.name.trim(),
        note: r.note?.trim() || null,
        ingredient_id: r.ingredient_id,
      }));
    if (!title.trim()) return setError("Bitte einen Titel angeben.");
    if (!ingredients.length) return setError("Bitte mindestens eine Zutat angeben.");
    const bad = rows.find((r) => r.amountText.trim() && parseAmount(r.amountText) === null);
    if (bad) return setError(`Menge „${bad.amountText}“ ist keine Zahl.`);
    setBusy(true);
    setError(null);
    try {
      await onSubmit(
        {
          ...initial,
          title: title.trim(),
          size,
          servings: Math.max(1, Number(servings) || 1),
          duration_min: duration ? Math.max(1, Number(duration)) : null,
          steps: steps.split("\n").map((s) => s.trim()).filter(Boolean),
          tag_ids: tagIds,
          ingredients,
          source_url: sourceUrl.trim() || null,
        },
        { image, useRemoteImage: useRemote && !image, removeImage },
      );
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="recipe-form stack" onSubmit={submit} noValidate>
      {hint && <p className="notice">{hint}</p>}
      <label className="field">
        <span>Titel</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} />
      </label>

      <div className="seg" role="radiogroup" aria-label="Größe">
        {(["haupt", "klein"] as const).map((s) => (
          <button key={s} type="button" role="radio" aria-checked={size === s} onClick={() => setSize(s)}>
            {s === "haupt" ? "Hauptmahlzeit" : "Kleine Mahlzeit"}
          </button>
        ))}
      </div>

      <div className="row2">
        <label className="field">
          <span>Portionen</span>
          <input type="number" inputMode="numeric" min={1} max={100} value={servings} onChange={(e) => setServings(e.target.value)} />
        </label>
        <label className="field">
          <span>Dauer (Minuten)</span>
          <input type="number" inputMode="numeric" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
        </label>
      </div>

      <fieldset className="field">
        <legend>Tags</legend>
        <div className="chips">
          {tags.data?.map((t) => (
            <button
              key={t.id}
              type="button"
              className="chip"
              aria-pressed={tagIds.includes(t.id)}
              onClick={() => setTagIds((ids) => (ids.includes(t.id) ? ids.filter((x) => x !== t.id) : [...ids, t.id]))}
            >
              {t.name}
            </button>
          ))}
        </div>
        <div className="inline">
          <input placeholder="Neuer Tag" aria-label="Neuer Tag" value={newTag} maxLength={40} onChange={(e) => setNewTag(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void addTag();
              }
            }}
          />
          <button type="button" className="btn" onClick={addTag} disabled={!newTag.trim()}>
            Anlegen
          </button>
        </div>
      </fieldset>

      <fieldset className="field">
        <legend>
          Zutaten {open > 0 && <span className="badge warn">{open} offen</span>}
        </legend>
        {open > 0 && <p className="muted small">Erst wenn alle Zutaten zugeordnet sind, kann der Plan das Rezept wählen.</p>}
        <ul className="plain ing-rows">
          {rows.map((r, idx) => (
            <li key={r.key} className={`ing-row${r.name.trim() && !r.ingredient_id ? " open" : ""}`}>
              {r.line && <span className="muted small">Original: {r.line}</span>}
              <div className="ing-inputs">
                <input className="amount" inputMode="decimal" aria-label={`Menge Zutat ${idx + 1}`} placeholder="Menge"
                  value={r.amountText} onChange={(e) => setRow(r.key, { amountText: e.target.value })} />
                <select aria-label={`Einheit Zutat ${idx + 1}`} value={r.unit ?? ""} onChange={(e) => setRow(r.key, { unit: e.target.value || null })}>
                  <option value="">–</option>
                  {[...UNITS, ...(r.unit && !UNITS.includes(r.unit) ? [r.unit] : [])].map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </select>
                <input className="name" aria-label={`Name Zutat ${idx + 1}`} placeholder="Zutat" value={r.name}
                  onChange={(e) => setRow(r.key, { name: e.target.value })} />
                <button type="button" className="icon-btn" aria-label={`Zutat ${idx + 1} entfernen`}
                  onClick={() => setRows((rs) => (rs.length > 1 ? rs.filter((x) => x.key !== r.key) : [emptyRow()]))}>
                  <Icon name="x" size={18} />
                </button>
              </div>
              <input className="note" aria-label={`Zusatz Zutat ${idx + 1}`} placeholder="Zusatz, etwa „gehackt“" value={r.note ?? ""}
                onChange={(e) => setRow(r.key, { note: e.target.value })} />
              {picking === r.key ? (
                <IngredientPicker
                  value={r.name}
                  label={`Katalogeintrag für ${r.name || "Zutat"}`}
                  autoFocus
                  onPick={(ing) => {
                    setRow(r.key, { ingredient_id: ing.id, catalogName: ing.name, name: r.name.trim() || ing.name, unit: r.unit ?? ing.default_unit });
                    setPicking(null);
                  }}
                />
              ) : r.ingredient_id ? (
                <button type="button" className="link-btn small" onClick={() => setPicking(r.key)}>
                  <Icon name="haken" size={16} /> Katalog: {r.catalogName} · ändern
                </button>
              ) : (
                r.name.trim() && (
                  <button type="button" className="link-btn small warn" onClick={() => setPicking(r.key)}>
                    Nicht zugeordnet · zuordnen
                  </button>
                )
              )}
            </li>
          ))}
        </ul>
        <button type="button" className="btn" onClick={() => setRows((rs) => [...rs, emptyRow()])}>
          <Icon name="neu" /> Zutat
        </button>
      </fieldset>

      <label className="field">
        <span>Zubereitung (ein Schritt pro Zeile)</span>
        <textarea rows={8} value={steps} onChange={(e) => setSteps(e.target.value)} />
      </label>

      <fieldset className="field">
        <legend>Foto</legend>
        {/* Gerichtsbild aus den Fotos liegt auf dem eigenen Server und wird gezeigt, fremde Bilder nicht */}
        {remoteImage && fromPhoto && !image && useRemote && <img className="form-thumb" src={remoteImage} alt="Bild aus dem Foto" />}
        {remoteImage && !image && (
          <label className="check">
            <input type="checkbox" checked={useRemote} onChange={(e) => setUseRemote(e.target.checked)} />
            {fromPhoto ? "Bild aus dem Foto übernehmen" : "Bild der Seite übernehmen"}
          </label>
        )}
        {currentImage && !image && !removeImage && <img className="form-thumb" src={currentImage} alt="Aktuelles Foto" />}
        {currentImage && !image && (
          <label className="check">
            <input type="checkbox" checked={removeImage} onChange={(e) => setRemoveImage(e.target.checked)} />
            Foto entfernen
          </label>
        )}
        {image && <FilePreview file={image} />}
        {/* getrennt, weil ein einzelnes Dateifeld auf neueren Android-Versionen nur die Galerie öffnet */}
        <div className="row2">
          <label className="btn file-btn">
            <Icon name="kamera" /> Aufnehmen
            <input type="file" accept="image/*" capture="environment" onChange={(e) => pick(e.target)} />
          </label>
          <label className="btn file-btn">
            Aus Galerie
            <input type="file" accept="image/*" onChange={(e) => pick(e.target)} />
          </label>
        </div>
        {image && (
          <button type="button" className="link-btn" onClick={() => setImage(null)}>
            Gewähltes Foto verwerfen
          </button>
        )}
      </fieldset>

      <label className="field">
        <span>Quelle (optional)</span>
        <input type="url" inputMode="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
      </label>

      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions-bottom">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Abbrechen
          </button>
        )}
        <button className="btn primary wide" disabled={busy}>
          {busy ? "Speichert …" : submitLabel}
        </button>
      </div>
    </form>
  );
}

function FilePreview({ file }: { file: File }) {
  const [src, setSrc] = useState<string>();
  useEffect(() => {
    const u = URL.createObjectURL(file);
    setSrc(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return src ? <img className="form-thumb" src={src} alt="Gewähltes Foto" /> : null;
}
