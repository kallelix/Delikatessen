const PATHS: Record<string, string> = {
  woche: "M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM8 13h3M8 16h6",
  rezepte: "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11M9 8h6",
  neu: "M12 5v14M5 12h14",
  einkauf: "M4 5h2l2 11h10l2-8H7M10 20a1 1 0 1 0 0-.01M17 20a1 1 0 1 0 0-.01",
  mehr: "M5 12h.01M12 12h.01M19 12h.01",
  stern: "M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z",
  pin: "M9 4h6l-1 6 3 3H7l3-3zM12 13v7",
  zurueck: "M15 5l-7 7 7 7",
  vor: "M9 5l7 7-7 7",
  suche: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4",
  uhr: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  teilen: "M12 3v12M7 8l5-5 5 5M5 14v5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5",
  loeschen: "M5 7h14M10 7V5h4v2M7 7l1 13h8l1-13",
  stift: "M4 20h4L19 9l-4-4L4 16zM14 6l4 4",
  haken: "M5 12l5 5L20 7",
  x: "M6 6l12 12M18 6L6 18",
  kamera: "M4 8h3l2-3h6l2 3h3v11H4zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  link: "M10 14a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1 1M14 10a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1-1",
  wuerfel: "M5 5h14v14H5zM9 9h.01M15 15h.01M15 9h.01M9 15h.01",
  person: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0",
  mikro: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
  text: "M5 6h14M5 10h14M5 14h10M5 18h7",
};

export function Icon({ name, size = 22, filled = false }: { name: keyof typeof PATHS | string; size?: number; filled?: boolean }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name] ?? ""} />
    </svg>
  );
}
