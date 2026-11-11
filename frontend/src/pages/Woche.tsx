import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, ApiError } from "../api";
import { useApp } from "../AppContext";
import { Icon } from "../components/Icon";
import { RatingButtons } from "../components/Rating";
import { Sheet, SheetAction } from "../components/Sheet";
import { useToast } from "../components/Toast";
import { addDays, dayLabel, defaultPlanWeek, errorText, isWeekend, MEAL_LABEL, today, useLoad, weekStart } from "../lib";
import type { Person, Plan, RecipeSummary, Slot } from "../types";

type SheetState =
  | { kind: "slot"; slot: Slot }
  | { kind: "choose"; slot: Slot }
  | { kind: "rate"; slotId: number }
  | { kind: "extra" }
  | null;

export function Woche() {
  const [params, setParams] = useSearchParams();
  const start = params.get("woche") ?? defaultPlanWeek();
  const { persons, me, isAdult } = useApp();
  const toast = useToast();
  const navigate = useNavigate();
  const plan = useLoad(() => api.plan(start), [start], true);
  const openRatings = useLoad(() => api.openRatings(), [start], true);
  const rankings = useLoad(() => api.rankings(), []);
  const [sheet, setSheet] = useState<SheetState>(null);
  const [busy, setBusy] = useState(false);

  // Rezepte der Woche vorab laden, damit sie ohne Empfang lesbar sind (N-07, AK-09)
  useEffect(() => {
    if (!plan.data || !navigator.onLine) return;
    const ids = new Set(plan.data.slots.flatMap((s) => (s.recipe ? [s.recipe.id] : [])));
    ids.forEach((id) => void api.recipe(id).catch(() => undefined));
    plan.data.slots.forEach((s) => {
      if (s.recipe?.image_url) void fetch(s.recipe.image_url).catch(() => undefined);
    });
  }, [plan.data]);

  async function change(fn: (version: number) => Promise<Plan>, done?: string) {
    if (!plan.data) return;
    setBusy(true);
    try {
      plan.setData(await fn(plan.data.version));
      if (done) toast.show(done);
      void openRatings.reload();
    } catch (e) {
      if (e instanceof ApiError && e.conflict) {
        toast.show("Jemand hat den Plan gerade geändert. Er ist neu geladen.", { error: true });
        await plan.reload();
      } else toast.show(errorText(e), { error: true });
    } finally {
      setBusy(false);
      setSheet(null);
    }
  }

  const days = useMemo(() => {
    const map = new Map<string, Slot[]>();
    plan.data?.slots.forEach((s) => map.set(s.date, [...(map.get(s.date) ?? []), s]));
    return [...map.entries()];
  }, [plan.data]);

  const filled = plan.data?.slots.filter((s) => s.recipe).length ?? 0;
  const isCurrent = start === weekStart();
  const longAgo = rankings.data?.long_not_eaten.slice(0, 3) ?? [];

  return (
    <section className="page">
      <header className="week-head">
        <button type="button" className="icon-btn" aria-label="Woche davor" onClick={() => setParams({ woche: addDays(start, -7) })}>
          <Icon name="zurueck" />
        </button>
        <div className="week-title">
          <h1>{isCurrent ? "Diese Woche" : start > weekStart() ? "Nächste Woche" : "Frühere Woche"}</h1>
          <span className="muted">
            {dayLabel(start)} bis {dayLabel(addDays(start, 6))}
          </span>
        </div>
        <button type="button" className="icon-btn" aria-label="Woche danach" onClick={() => setParams({ woche: addDays(start, 7) })}>
          <Icon name="vor" />
        </button>
      </header>

      {plan.error && !plan.data && <p className="error">{plan.error}</p>}

      {openRatings.data && openRatings.data.length > 0 && (
        <div className="card attention">
          <h2>Wie war es?</h2>
          <ul className="plain">
            {openRatings.data.slice(0, 3).map((o) => (
              <li key={o.slot_id}>
                <button type="button" className="row-btn" onClick={() => setSheet({ kind: "rate", slotId: o.slot_id })}>
                  <span>{o.recipe.title}</span>
                  <span className="muted">
                    {dayLabel(o.date)} {MEAL_LABEL[o.meal]}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {openRatings.data.length > 3 && <p className="muted small">und {openRatings.data.length - 3} weitere</p>}
        </div>
      )}

      {plan.data && (
        <ol className="days">
          {days.map(([date, slots]) => (
            <li key={date} className={`day${date === today() ? " today" : ""}`}>
              <h2 className="day-label">{dayLabel(date, true)}</h2>
              {slots.map((s) => (
                <SlotRow key={s.id} slot={s} onOpen={() => setSheet({ kind: "slot", slot: s })} />
              ))}
            </li>
          ))}
        </ol>
      )}

      {longAgo.length > 0 && isCurrent && (
        <div className="card">
          <h2>Hatten wir lange nicht</h2>
          <ul className="plain">
            {longAgo.map((e) => (
              <li key={e.recipe.id}>
                <Link className="row-btn" to={`/rezepte/${e.recipe.id}`}>
                  <span>{e.recipe.title}</span>
                  <span className="muted">{e.last_cooked ? `zuletzt ${dayLabel(e.last_cooked)}` : ""}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="actions-inline">
        <button
          type="button"
          className={`btn${filled ? "" : " primary"}`}
          disabled={busy || !plan.data}
          onClick={() => change((v) => api.generate(start, v), filled ? "Plan neu erzeugt. Fixiertes bleibt." : "Plan erzeugt")}
        >
          <Icon name="wuerfel" /> {filled ? "Neu erzeugen" : "Plan erzeugen"}
        </button>
        <button type="button" className="btn" disabled={busy || !plan.data} onClick={() => setSheet({ kind: "extra" })}>
          <Icon name="neu" /> Platz hinzufügen
        </button>
      </div>

      {filled > 0 && (
        <div className="actions-bottom">
          <button type="button" className="btn primary wide" onClick={() => navigate(`/einkauf?woche=${start}`)}>
            <Icon name="einkauf" /> Zutaten einkaufen
          </button>
        </div>
      )}

      {sheet?.kind === "slot" && plan.data && (
        <SlotSheet
          slot={sheet.slot}
          plan={plan.data}
          onClose={() => setSheet(null)}
          onChange={change}
          onChoose={() => setSheet({ kind: "choose", slot: sheet.slot })}
          onRate={() => setSheet({ kind: "rate", slotId: sheet.slot.id })}
          start={start}
        />
      )}
      {sheet?.kind === "choose" && (
        <ChooseSheet
          start={start}
          slot={sheet.slot}
          onClose={() => setSheet(null)}
          onPick={(r) => change((v) => api.updateSlot(start, sheet.slot.id, { version: v, recipe_id: r.id }), `${r.title} eingeplant`)}
        />
      )}
      {sheet?.kind === "rate" && (
        <RateSheet
          slotId={sheet.slotId}
          plan={plan.data}
          title={
            plan.data?.slots.find((s) => s.id === sheet.slotId)?.recipe?.title ??
            openRatings.data?.find((o) => o.slot_id === sheet.slotId)?.recipe.title ??
            "Bewerten"
          }
          initial={plan.data?.slots.find((s) => s.id === sheet.slotId)?.ratings}
          persons={persons}
          me={me}
          isAdult={isAdult}
          onClose={() => {
            setSheet(null);
            void openRatings.reload();
            void plan.reload();
          }}
        />
      )}
      {sheet?.kind === "extra" && plan.data && (
        <ExtraSheet plan={plan.data} onClose={() => setSheet(null)} onAdd={(body) => change((v) => api.addSlots(start, { ...body, version: v }), "Platz hinzugefügt")} />
      )}
    </section>
  );
}

function SlotRow({ slot, onOpen }: { slot: Slot; onOpen: () => void }) {
  const cls = ["slot", slot.cancelled ? "cancelled" : "", slot.size === "haupt" ? "main" : "small", slot.recipe ? "" : "empty"];
  return (
    <button type="button" className={cls.join(" ")} onClick={onOpen}>
      {slot.recipe?.image_url ? (
        <img className="thumb" src={slot.recipe.image_url} alt="" loading="lazy" />
      ) : (
        <span className="thumb placeholder" aria-hidden="true" />
      )}
      <span className="slot-body">
        <span className="slot-meta">
          {MEAL_LABEL[slot.meal]} · {slot.size === "haupt" ? "Hauptmahlzeit" : "klein"}
          {slot.extra && " · Zusatz"}
        </span>
        <span className="slot-title">
          {slot.cancelled ? "Essen entfällt" : (slot.recipe?.title ?? "Noch frei")}
        </span>
        {!slot.cancelled && slot.reason && <span className="slot-reason">{slot.reason}</span>}
        {slot.cancelled && slot.recipe && <span className="slot-reason">{slot.recipe.title}</span>}
        {slot.not_cooked && <span className="slot-reason">nicht gekocht</span>}
      </span>
      {slot.pinned && (
        <span className="pin" title="fixiert" aria-label="fixiert">
          <Icon name="pin" size={18} />
        </span>
      )}
    </button>
  );
}

function SlotSheet({
  slot,
  plan,
  start,
  onClose,
  onChange,
  onChoose,
  onRate,
}: {
  slot: Slot;
  plan: Plan;
  start: string;
  onClose: () => void;
  onChange: (fn: (version: number) => Promise<Plan>, done?: string) => Promise<void>;
  onChoose: () => void;
  onRate: () => void;
}) {
  const navigate = useNavigate();
  const sameDay = plan.slots.filter((s) => s.date === slot.date);
  const canSwap = isWeekend(slot.date) && sameDay.length === 2;
  const past = slot.date <= today();
  const title = `${dayLabel(slot.date, true)}, ${MEAL_LABEL[slot.meal]}`;
  const upd = (body: Omit<Parameters<typeof api.updateSlot>[2], "version">, done?: string) =>
    onChange((v) => api.updateSlot(start, slot.id, { ...body, version: v }), done);

  return (
    <Sheet title={title} onClose={onClose}>
      {slot.recipe && !slot.cancelled && (
        <SheetAction onClick={() => navigate(`/rezepte/${slot.recipe!.id}`)}>Rezept ansehen</SheetAction>
      )}
      {!slot.cancelled && (
        <>
          <SheetAction onClick={() => onChange((v) => api.suggest(start, slot.id, v))}>Neuer Vorschlag</SheetAction>
          <SheetAction onClick={onChoose}>Rezept wählen</SheetAction>
          {slot.recipe && (
            <SheetAction onClick={() => upd({ pinned: !slot.pinned }, slot.pinned ? "Lösen: wird beim Neu-Erzeugen ersetzt" : "Fixiert")}>
              {slot.pinned ? "Fixierung lösen" : "Fixieren"}
            </SheetAction>
          )}
        </>
      )}
      {slot.rateable && <SheetAction onClick={onRate}>Bewerten</SheetAction>}
      {past && slot.recipe && !slot.cancelled && (
        <SheetAction onClick={() => upd({ not_cooked: !slot.not_cooked })}>
          {slot.not_cooked ? "Doch gekocht" : "Nicht gekocht"}
        </SheetAction>
      )}
      {canSwap && !slot.cancelled && (
        <SheetAction onClick={() => upd({ swap_main: true }, "Hauptmahlzeit getauscht")}>
          {slot.size === "haupt" ? "Hauptmahlzeit auf die andere Mahlzeit legen" : "Hier die Hauptmahlzeit essen"}
        </SheetAction>
      )}
      <SheetAction onClick={() => upd({ cancelled: !slot.cancelled }, slot.cancelled ? "Wieder eingeplant" : "Essen entfällt")}>
        {slot.cancelled ? "Wieder einplanen" : "Essen entfällt"}
      </SheetAction>
      {slot.recipe && !slot.cancelled && (
        <SheetAction onClick={() => upd({ clear_recipe: true })}>Platz leeren</SheetAction>
      )}
      {slot.extra && (
        <SheetAction danger onClick={() => onChange((v) => api.deleteSlot(start, slot.id, v), "Platz entfernt")}>
          Zusatzplatz entfernen
        </SheetAction>
      )}
    </Sheet>
  );
}

function ChooseSheet({
  start,
  slot,
  onClose,
  onPick,
}: {
  start: string;
  slot: Slot;
  onClose: () => void;
  onPick: (r: RecipeSummary) => void;
}) {
  const [q, setQ] = useState("");
  const list = useLoad(() => api.candidates(start, slot.id), [slot.id]);
  const shown = (list.data ?? []).filter((r) => r.title.toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <Sheet title="Rezept wählen" onClose={onClose}>
      <input type="search" placeholder="Suchen" aria-label="Rezept suchen" value={q} onChange={(e) => setQ(e.target.value)} />
      <p className="muted small">Nur Rezepte ohne No-go-Zutaten, passende Größe zuerst.</p>
      {list.error && <p className="error">{list.error}</p>}
      <ul className="plain choose-list">
        {shown.map((r) => (
          <li key={r.id}>
            <button type="button" className="row-btn" onClick={() => onPick(r)}>
              <span>{r.title}</span>
              <span className="muted">{r.size === slot.size ? "" : r.size === "haupt" ? "Hauptmahlzeit" : "klein"}</span>
            </button>
          </li>
        ))}
        {list.data && shown.length === 0 && <li className="muted">Nichts gefunden.</li>}
      </ul>
    </Sheet>
  );
}

function RateSheet({
  slotId,
  title,
  initial,
  persons,
  me,
  isAdult,
  onClose,
}: {
  slotId: number;
  plan: Plan | null;
  title: string;
  initial?: Record<string, number>;
  persons: Person[];
  me: Person | null;
  isAdult: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const [ratings, setRatings] = useState<Record<string, number>>(initial ?? {});
  // Eltern werten vorerst stellvertretend für die Kinder (F-10)
  const editable = (p: Person) => p.id === me?.id || (isAdult && p.kind === "kind");
  const rows = persons.filter((p) => p.active);

  async function rate(p: Person, value: number | null) {
    try {
      setRatings(await api.rate(slotId, p.id, value));
    } catch (e) {
      toast.show(errorText(e), { error: true });
    }
  }

  return (
    <Sheet title={`Wie war ${title}?`} onClose={onClose}>
      <ul className="plain rate-list">
        {rows.map((p) => (
          <li key={p.id}>
            <span className="rate-name">
              {p.name}
              {p.id === me?.id && <span className="muted"> (du)</span>}
            </span>
            {editable(p) ? (
              <RatingButtons value={ratings[p.id]} onChange={(v) => rate(p, v)} label={`Wertung von ${p.name}`} />
            ) : (
              <span className="muted">
                {ratings[p.id] === undefined ? "noch offen" : ratings[p.id] === 1 ? "lecker" : ratings[p.id] === 0.5 ? "okay" : "mies"}
              </span>
            )}
          </li>
        ))}
      </ul>
      <button type="button" className="btn primary wide" onClick={onClose}>
        Fertig
      </button>
    </Sheet>
  );
}

function ExtraSheet({
  plan,
  onClose,
  onAdd,
}: {
  plan: Plan;
  onClose: () => void;
  onAdd: (body: { first: string; last: string; meal: string; size: string }) => void;
}) {
  const [first, setFirst] = useState(plan.start);
  const [last, setLast] = useState(plan.start);
  const [meal, setMeal] = useState("mittag");
  const [size, setSize] = useState("klein");
  return (
    <Sheet title="Platz hinzufügen" onClose={onClose}>
      <p className="muted small">Gilt nur für diese Woche, etwa an Feiertagen oder im Urlaub zu Hause.</p>
      <div className="seg" role="radiogroup" aria-label="Mahlzeit">
        {(["mittag", "abend"] as const).map((m) => (
          <button key={m} type="button" role="radio" aria-checked={meal === m} onClick={() => setMeal(m)}>
            {MEAL_LABEL[m]}
          </button>
        ))}
      </div>
      <div className="row2">
        <label className="field">
          <span>Von</span>
          <input type="date" value={first} min={plan.start} max={plan.end} onChange={(e) => {
            setFirst(e.target.value);
            if (e.target.value > last) setLast(e.target.value);
          }} />
        </label>
        <label className="field">
          <span>Bis</span>
          <input type="date" value={last} min={first} max={plan.end} onChange={(e) => setLast(e.target.value)} />
        </label>
      </div>
      <div className="seg" role="radiogroup" aria-label="Größe">
        {(["klein", "haupt"] as const).map((s) => (
          <button key={s} type="button" role="radio" aria-checked={size === s} onClick={() => setSize(s)}>
            {s === "haupt" ? "Hauptmahlzeit" : "Kleine Mahlzeit"}
          </button>
        ))}
      </div>
      <button type="button" className="btn primary wide" onClick={() => onAdd({ first, last, meal, size })}>
        Hinzufügen
      </button>
    </Sheet>
  );
}
