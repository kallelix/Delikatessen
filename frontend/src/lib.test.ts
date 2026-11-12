import { describe, expect, it } from "vitest";
import { familyPortions } from "./lib";
import type { Person } from "./types";

const person = (portion_factor: number, active = true): Person => ({
  id: 0,
  name: "x",
  kind: "erwachsen",
  portion_factor,
  active,
  netbird_ip: null,
  nogos: [],
});

describe("Portionen der Familie", () => {
  it("summiert die Faktoren der aktiven Personen wie die Einkaufsliste", () => {
    expect(familyPortions([person(1), person(1), person(0.5), person(0.7)])).toBe(3.2);
  });
  it("lässt inaktive Personen weg", () => {
    expect(familyPortions([person(1), person(1, false)])).toBe(1);
  });
  it("gibt null ohne Familie, dann gilt die Rezeptangabe", () => {
    expect(familyPortions([])).toBeNull();
    expect(familyPortions([person(1, false)])).toBeNull();
  });
});
