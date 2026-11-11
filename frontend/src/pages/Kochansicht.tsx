import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { useLoad } from "../lib";
import { IngredientList } from "./RezeptDetail";

/** Kochansicht mit großer Schrift, das Display bleibt an (F-04). */
export function Kochansicht() {
  const id = Number(useParams().id);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const recipe = useLoad(() => api.recipe(id), [id]);
  const [step, setStep] = useState(0);
  const awake = useWakeLock();

  if (!recipe.data) return <div className="page" aria-busy="true" />;
  const r = recipe.data;
  const portions = Number(params.get("portionen")) || r.servings;
  const steps = r.steps;

  return (
    <article className="cook">
      <header className="cook-head">
        <button type="button" className="icon-btn" aria-label="Kochansicht schließen" onClick={() => navigate(-1)}>
          <Icon name="x" />
        </button>
        <h1>{r.title}</h1>
        <span className="muted small">{awake ? "Display bleibt an" : ""}</span>
      </header>
      <details className="cook-ingredients" open={step === 0}>
        <summary>Zutaten für {portions}</summary>
        <IngredientList recipe={r} portions={portions} large />
      </details>
      {steps.length > 0 ? (
        <section className="cook-step" aria-live="polite">
          <p className="muted">
            Schritt {step + 1} von {steps.length}
          </p>
          <p className="cook-text">{steps[step]}</p>
        </section>
      ) : (
        <p className="cook-text">Keine Zubereitungsschritte hinterlegt.</p>
      )}
      <div className="cook-nav">
        <button type="button" className="btn big" disabled={step === 0} onClick={() => setStep(step - 1)}>
          Zurück
        </button>
        {step < steps.length - 1 ? (
          <button type="button" className="btn primary big" onClick={() => setStep(step + 1)}>
            Weiter
          </button>
        ) : (
          <button type="button" className="btn primary big" onClick={() => navigate(-1)}>
            Fertig
          </button>
        )}
      </div>
    </article>
  );
}

/** Screen Wake Lock, nach der Rückkehr in die App neu angefordert, weil der Browser sie dann freigibt. */
function useWakeLock(): boolean {
  const [active, setActive] = useState(false);
  useEffect(() => {
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;
    async function request() {
      if (!("wakeLock" in navigator) || document.visibilityState !== "visible") return;
      try {
        lock = await navigator.wakeLock.request("screen");
        if (cancelled) {
          void lock.release();
          return;
        }
        setActive(true);
        lock.addEventListener("release", () => setActive(false));
      } catch {
        setActive(false);
      }
    }
    const onVisible = () => {
      if (document.visibilityState === "visible") void request();
    };
    void request();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      void lock?.release();
    };
  }, []);
  return active;
}
