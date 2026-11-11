import { describe, expect, it } from "vitest";
import { formatQuantity, parseAmount, roundAmount, scale } from "./units";

describe("Umrechnen wie im Backend (F-02)", () => {
  it("rundet Gramm und Milliliter auf 5, kleine Mengen auf 1", () => {
    expect(roundAmount(123, "g")).toBe(125);
    expect(roundAmount(333.3, "ml")).toBe(335);
    expect(roundAmount(2.4, "g")).toBe(2);
  });
  it("rundet Stück auf 0,5", () => {
    expect(roundAmount(1.3, "Stück")).toBe(1.5);
    expect(roundAmount(0.1, "Stück")).toBe(0.5);
  });
  it("skaliert linear", () => {
    expect(scale(200, "g", 6 / 4)).toBe(300);
    expect(scale(null, "g", 2)).toBeNull();
    expect(scale(3, null, 1 / 4)).toBe(1);
    expect(scale(1.2, "kg", 1)).toBe(1.2);
  });
  it("formatiert deutsch", () => {
    expect(formatQuantity(1.5, "kg")).toBe("1,5 kg");
    expect(formatQuantity(2, null)).toBe("2");
    expect(formatQuantity(null, "g")).toBe("");
  });
  it("liest Eingaben", () => {
    expect(parseAmount("1,5")).toBe(1.5);
    expect(parseAmount("1/2")).toBe(0.5);
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("abc")).toBeNull();
  });
});
