// Umrechnen und Runden wie im Backend (delikatessen/units.py, F-02)

export const UNITS = [
  "g", "kg", "ml", "l", "EL", "TL", "Stück", "Prise", "Bund", "Dose", "Packung", "Zehe", "Scheibe",
  "Becher", "Tasse", "Msp.", "Glas", "Zweig", "Handvoll", "Stange", "Blatt", "Knolle", "Kopf", "Würfel", "Tüte",
];

export function roundAmount(amount: number, unit: string | null): number {
  if (amount <= 0) return 0;
  let step: number;
  if (unit === "g" || unit === "ml") step = amount >= 20 ? 5 : 1;
  else if (unit === "kg" || unit === "l") step = 0.05;
  else if (unit === "Stück" || unit === null) step = 0.5;
  else step = 0.25;
  let r = Math.round(amount / step) * step;
  if (r === 0) r = step;
  return Math.round(r * 10000) / 10000;
}

export function scale(amount: number | null, unit: string | null, factor: number): number | null {
  if (amount === null) return null;
  if (factor === 1) return amount;
  return roundAmount(amount * factor, unit);
}

export function formatNumber(x: number): string {
  if (Math.abs(x - Math.round(x)) < 1e-9) return String(Math.round(x));
  return x
    .toFixed(2)
    .replace(/0+$/, "")
    .replace(/\.$/, "")
    .replace(".", ",");
}

export function formatQuantity(amount: number | null, unit: string | null): string {
  if (amount === null) return "";
  return unit ? `${formatNumber(amount)} ${unit}` : formatNumber(amount);
}

export function parseAmount(text: string): number | null {
  const t = text.trim().replace(",", ".");
  if (!t) return null;
  const frac = t.match(/^(\d+)\s*\/\s*(\d+)$/);
  if (frac) return Number(frac[1]) / Number(frac[2]);
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : null;
}
