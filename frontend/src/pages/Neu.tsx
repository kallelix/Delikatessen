import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { api } from "../api";
import { Diktat } from "../components/Diktat";
import { Icon } from "../components/Icon";
import { EMPTY_RECIPE, RecipeForm } from "../components/RecipeForm";
import { useToast } from "../components/Toast";
import { errorText, findUrl, useLoad } from "../lib";
import type { ImportJob, RecipeInput } from "../types";

type Mode =
  | { kind: "start" }
  | { kind: "importing"; label: string }
  | { kind: "preview"; job: ImportJob }
  | { kind: "manual"; title?: string; source?: string | null; hint?: string; image?: File | null; jobId?: number };

const POLL_MS = 700;
// KI-Auswertungen von Fotos dauern deutlich länger als das Lesen einer Seite
const MAX_WAIT_MS = 75_000;
const MAX_WAIT_KI_MS = 240_000;
const MAX_PHOTOS = 4;

/** Neues Rezept: Link, Teilen-Menü, Foto, Text oder Diktat, oder von Hand. Jeder Import endet in der Vorschau. */
export function Neu() {
  const [params, setParams] = useSearchParams();
  const [mode, setMode] = useState<Mode>({ kind: "start" });
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const status = useLoad(() => api.status(), []);
  const navigate = useNavigate();
  const toast = useToast();
  const cancelled = useRef(false);
  const run = useRef(0);

  const ki = status.data?.dienste.ki;
  const kiReady = !!ki?.aktiv;

  useEffect(() => () => void (cancelled.current = true), []);

  // Vom Teilen-Menü: Daten liegen im Cache des Service Workers
  useEffect(() => {
    if (params.get("geteilt") !== "1") return;
    (async () => {
      const shared = await readShared();
      setParams({}, { replace: true });
      if (!shared) return;
      const link = findUrl(shared.url) ?? findUrl(shared.text) ?? findUrl(shared.title);
      if (link) return void importLink(link);
      // ohne Link: Fotos und Text liest die KI, falls eingerichtet
      const st = await api.status().catch(() => null);
      const kiOn = !!st?.dienste.ki?.aktiv;
      if (shared.images.length && kiOn) return void importPhotos(shared.images);
      if (shared.text.trim() && kiOn) return void importText(shared.text);
      const reason = st?.dienste.ki?.hinweis ? ` (KI: ${st.dienste.ki.hinweis})` : "";
      setMode({
        kind: "manual",
        title: shared.title,
        image: shared.images[0] ?? null,
        hint: `Ohne KI-Dienst${reason} bitte von Hand ergänzen.${shared.images.length ? " Das Foto ist schon angehängt." : ""}`,
      });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runJob(label: string, start: () => Promise<ImportJob>, source: string | null, maxWait: number) {
    const id = ++run.current;
    setMode({ kind: "importing", label });
    try {
      let job = await start();
      const until = Date.now() + maxWait;
      while ((job.status === "wartet" || job.status === "laeuft") && Date.now() < until) {
        await new Promise((r) => setTimeout(r, POLL_MS));
        // abgebrochen oder Seite verlassen: nicht mehr weiterschalten
        if (cancelled.current || run.current !== id) return;
        job = await api.importJob(job.id);
      }
      if (run.current !== id) return;
      if (job.status === "fertig") setMode({ kind: "preview", job });
      else if (job.status === "ohne_schema")
        setMode({
          kind: "manual",
          jobId: job.id,
          title: job.result?.title ?? "",
          source: job.result?.source_url ?? source,
          hint: job.error
            ? `Die Seite enthält kein lesbares Rezept, und die KI konnte nicht helfen: ${job.error}`
            : "Die Seite enthält kein lesbares Rezept. Ohne KI-Dienst bitte von Hand ergänzen.",
        });
      else if (job.status === "fehler")
        setMode({ kind: "manual", jobId: job.id, source, hint: `${job.error ?? "Import fehlgeschlagen"} Du kannst das Rezept von Hand anlegen.` });
      else {
        toast.show("Der Import dauert zu lange.", { error: true });
        setMode({ kind: "start" });
      }
    } catch (e) {
      if (run.current !== id) return;
      toast.show(errorText(e), { error: true });
      setMode({ kind: "start" });
    }
  }

  const importLink = (link: string) => runJob(link, () => api.startImport(link), link, kiReady ? MAX_WAIT_KI_MS : MAX_WAIT_MS);
  const importText = (t: string) => runJob("Text wird ausgewertet", () => api.startTextImport(t), null, MAX_WAIT_KI_MS);
  const importPhotos = (files: File[]) =>
    runJob(
      files.length > 1 ? `${files.length} Fotos werden ausgewertet` : "Foto wird ausgewertet",
      () => api.startPhotoImport(files),
      null,
      MAX_WAIT_KI_MS,
    );

  async function save(data: RecipeInput, extras: { image: File | null; useRemoteImage: boolean }, jobId?: number, remote?: string | null) {
    const recipe = jobId
      ? await api.acceptImport(jobId, data, extras.useRemoteImage ? remote : null)
      : await api.createRecipe(data);
    if (extras.image) {
      try {
        await api.uploadImage(recipe.id, extras.image);
      } catch (e) {
        toast.show(`Gespeichert, aber das Foto nicht: ${errorText(e)}`, { error: true });
      }
    }
    toast.show(recipe.plannable ? "Rezept gespeichert" : "Gespeichert. Noch offene Zutaten zuordnen, dann ist es planbar.");
    navigate(`/rezepte/${recipe.id}`, { replace: true });
  }

  function addPhotos(list: FileList | null) {
    if (!list) return;
    const next = [...photos, ...Array.from(list).filter((f) => f.type.startsWith("image/"))];
    if (next.length > MAX_PHOTOS) toast.show(`Höchstens ${MAX_PHOTOS} Fotos je Rezept`, { error: true });
    setPhotos(next.slice(0, MAX_PHOTOS));
  }

  if (mode.kind === "importing") {
    return (
      <section className="page center">
        <div className="spinner" aria-hidden="true" />
        <h1>Rezept wird gelesen …</h1>
        <p className="muted break">{mode.label}</p>
        <button
          type="button"
          className="btn"
          onClick={() => {
            run.current++;
            setMode({ kind: "start" });
          }}
        >
          Abbrechen
        </button>
      </section>
    );
  }

  if (mode.kind === "preview") {
    const r = mode.job.result!;
    return (
      <section className="page">
        <h1>Import prüfen</h1>
        <RecipeForm
          initial={{
            ...EMPTY_RECIPE,
            title: r.title ?? "",
            servings: r.servings ?? 4,
            size: r.size ?? "haupt",
            duration_min: r.duration_min ?? null,
            steps: r.steps ?? [],
            tag_ids: r.tag_ids ?? [],
            source_url: r.source_url ?? null,
          }}
          initialIngredients={r.ingredients ?? []}
          remoteImage={r.image_url}
          hint={
            r.ki
              ? "Von der KI gelesen. Bitte besonders Mengen und Einheiten prüfen. Ohne Bestätigung wird nichts gespeichert."
              : "Bitte prüfen. Ohne Bestätigung wird nichts gespeichert."
          }
          submitLabel="Speichern"
          onCancel={() => setMode({ kind: "start" })}
          onSubmit={(data, extras) => save(data, extras, mode.job.id, r.image_url)}
        />
      </section>
    );
  }

  if (mode.kind === "manual") {
    return (
      <section className="page">
        <h1>Neues Rezept</h1>
        <RecipeForm
          initial={{ ...EMPTY_RECIPE, title: mode.title ?? "", source_url: mode.source ?? null }}
          initialImage={mode.image}
          hint={mode.hint}
          submitLabel="Speichern"
          onCancel={() => setMode({ kind: "start" })}
          onSubmit={(data, extras) => save(data, extras, mode.jobId)}
        />
      </section>
    );
  }

  return (
    <section className="page">
      <h1>Neues Rezept</h1>
      <form
        className="card stack"
        onSubmit={(e) => {
          e.preventDefault();
          const link = findUrl(url);
          if (link) void importLink(link);
          else toast.show("Das ist kein Link.", { error: true });
        }}
      >
        <label className="field">
          <span>
            <Icon name="link" size={18} /> Link zu einem Rezept
          </span>
          <input type="url" inputMode="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <button className="btn primary" disabled={!url.trim()}>
          Rezept lesen
        </button>
        <p className="muted small">Tipp: Im Browser „Teilen“ und dann „Delikatessen“ wählen geht noch schneller.</p>
      </form>

      {status.data && !kiReady && (
        <p className="notice">
          Foto, Text und Diktat brauchen den KI-Dienst: {ki?.hinweis ?? "nicht eingerichtet"}. Link-Import und Anlegen von Hand gehen weiter.
        </p>
      )}

      <section className="card stack" aria-labelledby="foto-titel">
        <h2 id="foto-titel" className="card-title">
          <Icon name="kamera" size={18} /> Foto aus Kochbuch oder Notizzettel
        </h2>
        {photos.length > 0 && (
          <ul className="photo-strip">
            {photos.map((f, i) => (
              <li key={i}>
                <Thumb file={f} alt={`Foto ${i + 1}`} />
                <button type="button" className="icon-btn" aria-label={`Foto ${i + 1} entfernen`} onClick={() => setPhotos(photos.filter((_, j) => j !== i))}>
                  <Icon name="x" size={18} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="row2">
          <label className={`btn${!kiReady || photos.length >= MAX_PHOTOS ? " disabled" : ""}`}>
            <Icon name="kamera" /> Aufnehmen
            <input
              type="file"
              accept="image/*"
              capture="environment"
              hidden
              disabled={!kiReady || photos.length >= MAX_PHOTOS}
              onChange={(e) => {
                addPhotos(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
          <label className={`btn${!kiReady || photos.length >= MAX_PHOTOS ? " disabled" : ""}`}>
            Aus Galerie
            <input
              type="file"
              accept="image/*"
              multiple
              hidden
              disabled={!kiReady || photos.length >= MAX_PHOTOS}
              onChange={(e) => {
                addPhotos(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
        </div>
        <p className="muted small">Bis zu {MAX_PHOTOS} Fotos, etwa Zutaten und Zubereitung auf zwei Seiten.</p>
        <button type="button" className="btn primary" disabled={!kiReady || photos.length === 0} onClick={() => importPhotos(photos)}>
          Fotos auswerten
        </button>
      </section>

      <section className="card stack" aria-labelledby="text-titel">
        <h2 id="text-titel" className="card-title">
          <Icon name="text" size={18} /> Text oder Diktat
        </h2>
        <Diktat value={text} onChange={setText} disabled={!kiReady} />
        <button type="button" className="btn primary" disabled={!kiReady || !text.trim()} onClick={() => importText(text)}>
          Text auswerten
        </button>
      </section>

      <button type="button" className="btn wide" onClick={() => setMode({ kind: "manual" })}>
        <Icon name="stift" /> Von Hand anlegen
      </button>
    </section>
  );
}

function Thumb({ file, alt }: { file: File; alt: string }) {
  const [src, setSrc] = useState<string>();
  useEffect(() => {
    const u = URL.createObjectURL(file);
    setSrc(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return src ? <img src={src} alt={alt} /> : null;
}

async function readShared(): Promise<{ title: string; text: string; url: string; images: File[] } | null> {
  if (!("caches" in window)) return null;
  try {
    const cache = await caches.open("geteilt");
    const res = await cache.match("/geteilt/daten");
    if (!res) return null;
    const data = await res.json();
    const images: File[] = [];
    for (let i = 0; i < MAX_PHOTOS; i++) {
      const img = await cache.match(`/geteilt/bild-${i}`);
      if (!img) break;
      const blob = await img.blob();
      images.push(new File([blob], `geteilt-${i}`, { type: blob.type || "image/jpeg" }));
      await cache.delete(`/geteilt/bild-${i}`);
    }
    await cache.delete("/geteilt/daten");
    return { title: data.title ?? "", text: data.text ?? "", url: data.url ?? "", images };
  } catch {
    return null;
  }
}
