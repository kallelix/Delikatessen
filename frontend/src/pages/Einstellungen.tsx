import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../AppContext";
import { useToast } from "../components/Toast";
import { errorText, MEAL_LABEL, useLoad } from "../lib";
import type { AppSettings, Meal, Weights } from "../types";

const DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
const WEIGHT_LABEL: Record<keyof Weights, string> = {
  F: "Lieblingsessen",
  L: "Lange nicht gegessen",
  T: "Aufwand passt zum Tag",
  A: "Abzug für Wiederholung",
};

/** Planungsraster, Zeitlimits, Gewichte und Uhrzeit, nur für Erwachsene (F-41). */
export function Einstellungen() {
  const { isAdult } = useApp();
  const loaded = useLoad(() => api.settings(), []);
  const [s, setS] = useState<AppSettings | null>(null);
  const toast = useToast();

  useEffect(() => {
    if (loaded.data) setS(loaded.data);
  }, [loaded.data]);

  if (!isAdult) return <p className="page notice">Einstellungen ändern nur Erwachsene.</p>;
  if (!s) return <div className="page" aria-busy="true">{loaded.error && <p className="error">{loaded.error}</p>}</div>;

  const toggleMeal = (day: number, meal: Meal) => {
    const cur = s.grid[day] ?? [];
    setS({ ...s, grid: { ...s.grid, [day]: cur.includes(meal) ? cur.filter((m) => m !== meal) : [...cur, meal] } });
  };

  async function save() {
    try {
      setS(await api.saveSettings(s!));
      toast.show("Gespeichert. Gilt für neu angelegte Wochen.");
    } catch (e) {
      toast.show(errorText(e), { error: true });
    }
  }

  return (
    <section className="page">
      <h1>Einstellungen</h1>

      <h2>Standardraster</h2>
      <p className="muted small">Welche Mahlzeiten geplant werden. Gilt für Wochen, die noch nicht angelegt sind.</p>
      <table className="grid-table">
        <thead>
          <tr>
            <th scope="col">Tag</th>
            <th scope="col">Mittag</th>
            <th scope="col">Abend</th>
            <th scope="col">Zeitlimit</th>
          </tr>
        </thead>
        <tbody>
          {DAYS.map((name, day) => (
            <tr key={day}>
              <th scope="row">{name}</th>
              {(["mittag", "abend"] as const).map((m) => (
                <td key={m}>
                  <input type="checkbox" aria-label={`${name} ${MEAL_LABEL[m]}`} checked={(s.grid[day] ?? []).includes(m)} onChange={() => toggleMeal(day, m)} />
                </td>
              ))}
              <td>
                <input
                  className="minutes"
                  type="number"
                  inputMode="numeric"
                  min={5}
                  aria-label={`Zeitlimit ${name} in Minuten`}
                  placeholder="–"
                  value={s.time_limits[day] ?? ""}
                  onChange={(e) => setS({ ...s, time_limits: { ...s.time_limits, [day]: e.target.value ? Number(e.target.value) : null } })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <fieldset className="field">
        <legend>Hauptmahlzeit am Wochenende</legend>
        <div className="seg" role="radiogroup" aria-label="Hauptmahlzeit am Wochenende">
          {(["mittag", "abend"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={s.weekend_main === m} onClick={() => setS({ ...s, weekend_main: m })}>
              {MEAL_LABEL[m]}
            </button>
          ))}
        </div>
      </fieldset>

      <h2>Gewichte der Planung</h2>
      {(Object.keys(WEIGHT_LABEL) as (keyof Weights)[]).map((k) => (
        <label key={k} className="field slider">
          <span>
            {WEIGHT_LABEL[k]} <output>{s.weights[k].toFixed(2).replace(".", ",")}</output>
          </span>
          <input type="range" min={0} max={1} step={0.05} value={s.weights[k]} onChange={(e) => setS({ ...s, weights: { ...s.weights, [k]: Number(e.target.value) } })} />
        </label>
      ))}

      <label className="field">
        <span>Planvorschlag donnerstags um (ab Stufe 2)</span>
        <input type="time" value={s.plan_time} onChange={(e) => setS({ ...s, plan_time: e.target.value })} />
      </label>

      <div className="actions-bottom">
        <button type="button" className="btn primary wide" onClick={save}>
          Speichern
        </button>
      </div>
    </section>
  );
}
