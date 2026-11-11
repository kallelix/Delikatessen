import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";
import { addDays, dayLabel, defaultPlanWeek, errorText, useLoad } from "../lib";
import type { ShoppingItem } from "../types";

/** Einkaufsliste in der App: abhaken, "schon im Haus", als Text teilen (F-30 bis F-32). */
export function Einkauf() {
  const [params, setParams] = useSearchParams();
  const start = params.get("woche") ?? defaultPlanWeek();
  const list = useLoad(() => api.shopping(start), [start], true);
  const toast = useToast();

  const items = list.data ?? [];
  const toBuy = items.filter((i) => !i.at_home);
  const atHome = items.filter((i) => i.at_home);
  const groups = useMemo(() => {
    const map = new Map<string, ShoppingItem[]>();
    toBuy.forEach((i) => map.set(i.group, [...(map.get(i.group) ?? []), i]));
    return [...map.entries()];
  }, [toBuy]);
  const open = toBuy.filter((i) => !i.checked).length;

  async function patch(item: ShoppingItem, data: { checked?: boolean; at_home?: boolean }) {
    // sofort anzeigen, dann speichern
    list.setData(items.map((i) => (i.id === item.id ? { ...i, ...data } : i)));
    try {
      await api.patchShopping(item.id, data);
    } catch (e) {
      toast.show(errorText(e), { error: true });
      void list.reload();
    }
  }

  async function share() {
    const lines = toBuy.filter((i) => !i.checked).map((i) => `- ${i.quantity ? `${i.quantity} ` : ""}${i.name}`);
    const text = `Einkauf für die Woche ab ${dayLabel(start)}\n${lines.join("\n")}`;
    try {
      if (navigator.share) await navigator.share({ title: "Einkaufsliste", text });
      else {
        await navigator.clipboard.writeText(text);
        toast.show("Liste kopiert");
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") toast.show("Teilen hat nicht geklappt", { error: true });
    }
  }

  return (
    <section className="page">
      <header className="week-head">
        <button type="button" className="icon-btn" aria-label="Woche davor" onClick={() => setParams({ woche: addDays(start, -7) })}>
          <Icon name="zurueck" />
        </button>
        <div className="week-title">
          <h1>Einkauf</h1>
          <span className="muted">Woche ab {dayLabel(start)}</span>
        </div>
        <button type="button" className="icon-btn" aria-label="Woche danach" onClick={() => setParams({ woche: addDays(start, 7) })}>
          <Icon name="vor" />
        </button>
      </header>

      {list.error && !list.data && <p className="error">{list.error}</p>}
      {list.data && items.length === 0 && <p className="empty">Noch nichts geplant. Erst den Plan erzeugen.</p>}

      {groups.map(([group, rows]) => (
        <div key={group} className="shop-group">
          <h2>{group}</h2>
          <ul className="plain">
            {rows.map((i) => (
              <ShopRow key={i.id} item={i} onCheck={() => patch(i, { checked: !i.checked })} onHome={() => patch(i, { at_home: true })} />
            ))}
          </ul>
        </div>
      ))}

      {atHome.length > 0 && (
        <details className="shop-group home">
          <summary>Schon im Haus ({atHome.length})</summary>
          <ul className="plain">
            {atHome.map((i) => (
              <li key={i.id} className="shop-row">
                <span className="shop-text">
                  <span>{i.name}</span>
                  <span className="muted small">{i.quantity}</span>
                </span>
                <button type="button" className="link-btn" onClick={() => patch(i, { at_home: false })}>
                  doch kaufen
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {items.length > 0 && (
        <div className="actions-bottom">
          <span className="muted">{open} offen</span>
          <button type="button" className="btn primary wide" onClick={share} disabled={open === 0}>
            <Icon name="teilen" /> Als Text teilen
          </button>
        </div>
      )}
      <p className="muted small">Bring! kommt mit Stufe 2.</p>
    </section>
  );
}

function ShopRow({ item, onCheck, onHome }: { item: ShoppingItem; onCheck: () => void; onHome: () => void }) {
  return (
    <li className={`shop-row${item.checked ? " checked" : ""}`}>
      <label className="shop-check">
        <input type="checkbox" checked={item.checked} onChange={onCheck} />
        <span className="shop-text">
          <span>{item.name}</span>
          <span className="muted small">
            {item.quantity}
            {item.recipes.length > 0 && ` · ${item.recipes.join(", ")}`}
          </span>
        </span>
      </label>
      {!item.checked && (
        <button type="button" className="link-btn" onClick={onHome} aria-label={`${item.name} ist schon im Haus`}>
          im Haus
        </button>
      )}
    </li>
  );
}
