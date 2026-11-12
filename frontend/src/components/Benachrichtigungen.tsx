import { useEffect, useState } from "react";
import { api } from "../api";
import { errorText } from "../lib";
import { useToast } from "./Toast";

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

const supported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

/** Benachrichtigung zum Donnerstagslauf (F-24) für dieses Gerät an- und abschalten. */
export function Benachrichtigungen() {
  const [sub, setSub] = useState<PushSubscription | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (!supported()) return setReady(true);
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then(setSub)
      .catch(() => undefined)
      .finally(() => setReady(true));
  }, []);

  async function enable() {
    setBusy(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        toast.show("Benachrichtigungen sind für die App blockiert. In den Einstellungen von Chrome freigeben.", { error: true });
        return;
      }
      const reg = await navigator.serviceWorker.ready;
      const { public_key } = await api.pushKey();
      const s = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) });
      await api.pushSubscribe(s.toJSON());
      setSub(s);
      toast.show("Benachrichtigungen an");
    } catch (e) {
      toast.show(errorText(e), { error: true });
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    if (!sub) return;
    setBusy(true);
    try {
      await api.pushUnsubscribe(sub.endpoint);
      await sub.unsubscribe();
      setSub(null);
      toast.show("Benachrichtigungen aus");
    } catch (e) {
      toast.show(errorText(e), { error: true });
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    if (!sub) return;
    try {
      const r = await api.pushTest(sub.endpoint);
      if (r.gesendet === 0) toast.show("Der Push-Dienst hat die Nachricht nicht angenommen", { error: true });
    } catch (e) {
      toast.show(errorText(e), { error: true });
    }
  }

  if (!ready) return null;
  if (!supported()) {
    return <p className="muted small">Dieses Gerät oder dieser Browser kann keine Benachrichtigungen empfangen. Am Android-Handy die installierte App nutzen.</p>;
  }
  return (
    <div className="push-settings">
      <label className="field check">
        <input type="checkbox" checked={!!sub} disabled={busy} onChange={(e) => (e.target.checked ? enable() : disable())} />
        <span>Benachrichtigung, wenn der Wochenplan da ist</span>
      </label>
      {sub && (
        <button type="button" className="link-btn" onClick={test}>
          Testnachricht schicken
        </button>
      )}
    </div>
  );
}
