import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

/** Minimale Typen der Web Speech API, die TypeScript nicht überall mitbringt. */
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
}

function recognitionClass(): (new () => Recognition) | null {
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Textfeld mit Diktat (D-SPR). Die Spracherkennung des Browsers ist in Chrome für Android nur
 * teilweise verfügbar, deshalb bleibt das Mikrofon der Tastatur im selben Feld gleichwertig (Abschnitt 7).
 */
export function Diktat({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const base = useRef("");
  const Rec = recognitionClass();

  useEffect(() => () => rec.current?.stop(), []);

  function toggle() {
    if (listening) {
      rec.current?.stop();
      return;
    }
    if (!Rec) return;
    setError(null);
    const r = new Rec();
    r.lang = "de-DE";
    r.continuous = true;
    r.interimResults = true;
    base.current = value ? `${value.trimEnd()}\n` : "";
    r.onresult = (e) => {
      let final = "";
      let interim = "";
      for (let i = 0; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) final += `${res[0].transcript.trim()}\n`;
        else interim += res[0].transcript;
      }
      onChange(base.current + final + interim);
    };
    r.onerror = (e) => {
      if (e.error === "not-allowed") setError("Kein Zugriff aufs Mikrofon. Alternativ das Mikrofon der Tastatur nutzen.");
      else if (e.error !== "no-speech" && e.error !== "aborted") setError("Die Spracherkennung hat abgebrochen. Das Mikrofon der Tastatur geht auch.");
    };
    r.onend = () => setListening(false);
    rec.current = r;
    r.start();
    setListening(true);
  }

  return (
    <div className="diktat">
      <textarea
        rows={8}
        value={value}
        disabled={disabled}
        placeholder="Rezept einfügen oder diktieren: Zutaten mit Mengen, dann die Schritte."
        aria-label="Rezepttext"
        onChange={(e) => onChange(e.target.value)}
      />
      {Rec ? (
        <button type="button" className={`btn${listening ? " recording" : ""}`} onClick={toggle} disabled={disabled} aria-pressed={listening}>
          <Icon name="mikro" /> {listening ? "Diktat beenden" : "Diktieren"}
        </button>
      ) : (
        <p className="muted small">Zum Diktieren das Mikrofon der Tastatur verwenden.</p>
      )}
      {error && <p className="error small">{error}</p>}
    </div>
  );
}
