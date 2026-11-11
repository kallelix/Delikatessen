// Das gewählte Profil wird im Gerät gespeichert (N-09). Speicher kann fehlen, daher immer abgesichert.
const KEY = "delikatessen.profil";

export function getProfileId(): number | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw && /^\d+$/.test(raw) ? Number(raw) : null;
  } catch {
    return null;
  }
}

export function setProfileId(id: number | null): void {
  try {
    if (id === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, String(id));
  } catch {
    // ohne Speicher gilt die Wahl nur bis zum Neuladen
  }
}
