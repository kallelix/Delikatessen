import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { EMPTY_RECIPE, RecipeForm } from "../components/RecipeForm";
import { useToast } from "../components/Toast";
import { errorText, findUrl } from "../lib";
import type { ImportJob, RecipeInput } from "../types";

type Mode =
  | { kind: "start" }
  | { kind: "importing"; url: string; jobId?: number }
  | { kind: "preview"; job: ImportJob }
  | { kind: "manual"; title?: string; source?: string | null; hint?: string; image?: File | null; jobId?: number };

const POLL_MS = 700;
const MAX_WAIT_MS = 75_000;

/** Neues Rezept: per Link oder Teilen-Menü (Stufe 1) oder von Hand. Jeder Import endet in der Vorschau. */
export function Neu() {
  const [params, setParams] = useSearchParams();
  const [mode, setMode] = useState<Mode>({ kind: "start" });
  const [url, setUrl] = useState("");
  const navigate = useNavigate();
  const toast = useToast();
  const cancelled = useRef(false);

  useEffect(() => () => void (cancelled.current = true), []);

  // Vom Teilen-Menü: Daten liegen im Cache des Service Workers
  useEffect(() => {
    if (params.get("geteilt") !== "1") return;
    (async () => {
      const shared = await readShared();
      setParams({}, { replace: true });
      if (!shared) return;
      const link = findUrl(shared.url) ?? findUrl(shared.text) ?? findUrl(shared.title);
      if (link) void startImport(link);
      else if (shared.images.length)
        setMode({ kind: "manual", title: shared.title, image: shared.images[0], hint: "Rezepte aus Fotos liest die App ab Stufe 2. Das Foto ist schon angehängt." });
      else setMode({ kind: "manual", title: shared.title, hint: "Ohne Link: Text übernimmt die App ab Stufe 2." });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startImport(link: string) {
    setMode({ kind: "importing", url: link });
    try {
      let job = await api.startImport(link);
      setMode({ kind: "importing", url: link, jobId: job.id });
      const until = Date.now() + MAX_WAIT_MS;
      while ((job.status === "wartet" || job.status === "laeuft") && Date.now() < until) {
        await new Promise((r) => setTimeout(r, POLL_MS));
        if (cancelled.current) return;
        job = await api.importJob(job.id);
      }
      if (job.status === "fertig") setMode({ kind: "preview", job });
      else if (job.status === "ohne_schema")
        setMode({
          kind: "manual",
          jobId: job.id,
          title: job.result?.title ?? "",
          source: job.result?.source_url ?? link,
          hint: "Die Seite enthält kein lesbares Rezept. Ohne KI-Dienst bitte von Hand ergänzen.",
        });
      else if (job.status === "fehler")
        setMode({ kind: "manual", jobId: job.id, source: link, hint: `${job.error ?? "Import fehlgeschlagen"}. Du kannst das Rezept von Hand anlegen.` });
      else {
        toast.show("Der Import dauert zu lange.", { error: true });
        setMode({ kind: "start" });
      }
    } catch (e) {
      toast.show(errorText(e), { error: true });
      setMode({ kind: "start" });
    }
  }

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

  if (mode.kind === "importing") {
    return (
      <section className="page center">
        <div className="spinner" aria-hidden="true" />
        <h1>Rezept wird gelesen …</h1>
        <p className="muted break">{mode.url}</p>
        <button type="button" className="btn" onClick={() => setMode({ kind: "start" })}>
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
            source_url: r.source_url ?? null,
          }}
          initialIngredients={r.ingredients ?? []}
          remoteImage={r.image_url}
          hint="Bitte prüfen. Ohne Bestätigung wird nichts gespeichert."
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
          if (link) void startImport(link);
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
      <button type="button" className="btn wide" onClick={() => setMode({ kind: "manual" })}>
        <Icon name="stift" /> Von Hand anlegen
      </button>
      <div className="card muted">
        <p>
          <Icon name="kamera" size={18} /> Foto und Diktat kommen mit Stufe 2.
        </p>
      </div>
    </section>
  );
}

async function readShared(): Promise<{ title: string; text: string; url: string; images: File[] } | null> {
  if (!("caches" in window)) return null;
  try {
    const cache = await caches.open("geteilt");
    const res = await cache.match("/geteilt/daten");
    if (!res) return null;
    const data = await res.json();
    const images: File[] = [];
    for (let i = 0; i < 4; i++) {
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
