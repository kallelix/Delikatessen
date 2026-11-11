import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { getProfileId, setProfileId } from "./profile";
import type { Person } from "./types";

interface AppState {
  persons: Person[];
  me: Person | null;
  ready: boolean;
  offline: boolean;
  isAdult: boolean;
  chooseProfile: (id: number | null) => void;
  refreshPersons: () => Promise<void>;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [persons, setPersons] = useState<Person[]>([]);
  const [profile, setProfile] = useState<number | null>(getProfileId());
  const [ready, setReady] = useState(false);
  const [offline, setOffline] = useState(!navigator.onLine);

  const refreshPersons = useCallback(async () => {
    try {
      setPersons(await api.persons());
    } catch {
      // ohne Netz bleibt die letzte Liste
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refreshPersons();
      if (getProfileId() === null) {
        // optional: Zuordnung über die NetBird-IP des Geräts (N-09)
        try {
          const me = await api.me();
          if (me) {
            setProfileId(me.id);
            setProfile(me.id);
          }
        } catch {
          // egal, dann wählt man selbst
        }
      }
      setReady(true);
    })();
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, [refreshPersons]);

  const chooseProfile = useCallback((id: number | null) => {
    setProfileId(id);
    setProfile(id);
  }, []);

  const me = persons.find((p) => p.id === profile) ?? null;
  const isAdult = me ? me.kind === "erwachsen" : persons.length === 0;

  return (
    <Ctx.Provider value={{ persons, me, ready, offline, isAdult, chooseProfile, refreshPersons }}>
      {children}
    </Ctx.Provider>
  );
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("AppProvider fehlt");
  return ctx;
}
