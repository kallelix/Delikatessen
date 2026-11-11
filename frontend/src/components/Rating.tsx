export const RATINGS: { value: number; label: string }[] = [
  { value: 0, label: "mies" },
  { value: 0.5, label: "okay" },
  { value: 1, label: "lecker" },
];

/** Drei Stufen, mit einem Tipp erledigt (F-10). Nochmal tippen nimmt die Wertung zurück. */
export function RatingButtons({
  value,
  onChange,
  label,
}: {
  value: number | undefined;
  onChange: (v: number | null) => void;
  label: string;
}) {
  return (
    <div className="rating" role="group" aria-label={label}>
      {RATINGS.map((r) => (
        <button
          key={r.value}
          type="button"
          className={`rating-btn r${String(r.value).replace(".", "")}`}
          aria-pressed={value === r.value}
          onClick={() => onChange(value === r.value ? null : r.value)}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
