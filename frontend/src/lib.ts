import { useCallback, useEffect, useRef, useState } from "react";
import type { Meal, Person } from "./types";

/** Portionen der Familie wie in der Einkaufsliste: Summe der Portionsfaktoren aller aktiven Personen. */
export function familyPortions(persons: Person[]): number | null {
  const sum = persons.filter((p) => p.active).reduce((s, p) => s + p.portion_factor, 0);
  return sum > 0 ? Math.round(sum * 100) / 100 : null;
}

const DAY = 86_400_000;
const WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const WEEKDAYS_LONG = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];

/** Datum als YYYY-MM-DD in lokaler Zeit. */
export function iso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function parseIso(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d, 12);
}

export function addDays(s: string, days: number): string {
  return iso(new Date(parseIso(s).getTime() + days * DAY));
}

/** Die Planwoche beginnt am Samstag (F-24). */
export function weekStart(d: Date = new Date()): string {
  const back = (d.getDay() + 1) % 7; // Sa -> 0, So -> 1, ... Fr -> 6
  return iso(new Date(d.getFullYear(), d.getMonth(), d.getDate() - back, 12));
}

/** Donnerstags und freitags wird für die nächste Woche geplant und eingekauft. */
export function defaultPlanWeek(d: Date = new Date()): string {
  const start = weekStart(d);
  return d.getDay() === 4 || d.getDay() === 5 ? addDays(start, 7) : start;
}

export function dayLabel(s: string, long = false): string {
  const d = parseIso(s);
  const wd = (long ? WEEKDAYS_LONG : WEEKDAYS)[d.getDay()];
  return `${wd} ${d.getDate()}.${d.getMonth() + 1}.`;
}

export function dateLabel(s: string): string {
  const d = parseIso(s);
  return `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()}`;
}

export const MEAL_LABEL: Record<Meal, string> = { mittag: "Mittag", abend: "Abend" };

export function isWeekend(s: string): boolean {
  const day = parseIso(s).getDay();
  return day === 0 || day === 6;
}

export function today(): string {
  return iso(new Date());
}

/** Lädt Daten, lädt beim Zurückkehren in die App neu und meldet Fehler. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[], reloadOnFocus = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!reloadOnFocus) return;
    const onVisible = () => {
      if (document.visibilityState === "visible") void reload();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [reload, reloadOnFocus]);

  return { data, setData, error, setError, loading, reload };
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function findUrl(text: string): string | null {
  const m = text.match(/https?:\/\/[^\s<>"]+/i);
  return m ? m[0].replace(/[),.;!?]+$/, "") : null;
}
