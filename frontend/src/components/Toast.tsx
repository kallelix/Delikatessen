import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

interface ToastData {
  id: number;
  text: string;
  actionLabel?: string;
  onAction?: () => void;
  error?: boolean;
}

interface ToastApi {
  show: (text: string, opts?: { actionLabel?: string; onAction?: () => void; error?: boolean; ms?: number }) => void;
  /** Führt eine Aktion verzögert aus und bietet so lange "Rückgängig" an. */
  undoable: (text: string, commit: () => void | Promise<void>, onUndo: () => void, ms?: number) => void;
}

const Ctx = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastData | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const counter = useRef(0);

  const show: ToastApi["show"] = useCallback((text, opts = {}) => {
    window.clearTimeout(timer.current);
    const id = ++counter.current;
    setToast({ id, text, actionLabel: opts.actionLabel, onAction: opts.onAction, error: opts.error });
    timer.current = window.setTimeout(() => setToast((t) => (t?.id === id ? null : t)), opts.ms ?? 4000);
  }, []);

  const undoable: ToastApi["undoable"] = useCallback(
    (text, commit, onUndo, ms = 5000) => {
      let undone = false;
      const pending = window.setTimeout(() => {
        if (!undone) void commit();
      }, ms);
      show(text, {
        ms,
        actionLabel: "Rückgängig",
        onAction: () => {
          undone = true;
          window.clearTimeout(pending);
          onUndo();
        },
      });
    },
    [show],
  );

  return (
    <Ctx.Provider value={{ show, undoable }}>
      {children}
      <div className="toast-area" aria-live="polite">
        {toast && (
          <div className={`toast${toast.error ? " error" : ""}`} role={toast.error ? "alert" : "status"}>
            <span>{toast.text}</span>
            {toast.actionLabel && (
              <button
                type="button"
                onClick={() => {
                  toast.onAction?.();
                  setToast(null);
                }}
              >
                {toast.actionLabel}
              </button>
            )}
          </div>
        )}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("ToastProvider fehlt");
  return ctx;
}
