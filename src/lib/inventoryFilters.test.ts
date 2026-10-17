import { describe, expect, it } from "vitest";
import { NO_FILTERS, applyLocationFilters, hasFilters, optionsFor, pruneFilters, setFilter, type LocationRow } from "@/lib/inventoryFilters";

const row = (regionName: string | null, state: string | null, city: string | null, vendorName: string | null): LocationRow => ({ regionName, state, city, vendorName });
const rows = [
  row("South", "Karnataka", "Bengaluru", "Aqua Co"),
  row("South", "Karnataka", "Bengaluru", "Pure Ltd"),
  row("South", "Karnataka", "Mysuru", "Aqua Co"),
  row("South", "Tamil Nadu", "Chennai", "Pure Ltd"),
  row("North", "Delhi", "New Delhi", "Aqua Co"),
  row("North", "Delhi", "New Delhi", null),
  row(null, "Haryana", "Gurugram", "Pure Ltd"),
];
const values = (r: LocationRow[], f = NO_FILTERS, key: "region" | "state" | "city" | "vendor") => optionsFor(r, f, key).map((o) => o.value);

describe("inventory location filters", () => {
  it("lists every value once, A to Z, with the number of stores behind it", () => {
    expect(values(rows, NO_FILTERS, "state")).toEqual(["Delhi", "Haryana", "Karnataka", "Tamil Nadu"]);
    expect(optionsFor(rows, NO_FILTERS, "state").find((o) => o.value === "Karnataka")?.count).toBe(3);
    expect(values(rows, NO_FILTERS, "region")).toEqual(["North", "South"]);   // a store without a region is not listed
    expect(values(rows, NO_FILTERS, "vendor")).toEqual(["Aqua Co", "Pure Ltd"]);
  });

  it("choosing a state narrows the city and vendor lists to that state", () => {
    const f = { ...NO_FILTERS, state: "Karnataka" };
    expect(values(rows, f, "city")).toEqual(["Bengaluru", "Mysuru"]);
    expect(values(rows, f, "vendor")).toEqual(["Aqua Co", "Pure Ltd"]);
    expect(values(rows, { ...NO_FILTERS, state: "Tamil Nadu" }, "vendor")).toEqual(["Pure Ltd"]);
  });

  it("a dropdown still offers its own alternatives, so the choice can be switched directly", () => {
    const f = { ...NO_FILTERS, state: "Karnataka" };
    expect(values(rows, f, "state")).toEqual(["Delhi", "Haryana", "Karnataka", "Tamil Nadu"]);
  });

  it("the filters combine and the list follows them", () => {
    const f = { ...NO_FILTERS, region: "South", vendor: "Pure Ltd" };
    expect(applyLocationFilters(rows, f).map((r) => r.city)).toEqual(["Bengaluru", "Chennai"]);
    expect(applyLocationFilters(rows, NO_FILTERS)).toBe(rows);
    expect(hasFilters(f)).toBe(true);
    expect(hasFilters(NO_FILTERS)).toBe(false);
  });

  it("changing the state clears a city that does not belong to it, and keeps one that does", () => {
    const start = setFilter(rows, NO_FILTERS, "city", "Chennai");
    expect(start).toEqual({ ...NO_FILTERS, region: "", state: "", city: "Chennai", vendor: "" });
    expect(setFilter(rows, start, "state", "Karnataka").city).toBe("");
    expect(setFilter(rows, start, "state", "Tamil Nadu").city).toBe("Chennai");
  });

  it("drops every selection that no longer matches anything, even when several depend on each other", () => {
    const f = pruneFilters(rows, { region: "North", state: "Karnataka", city: "Mysuru", vendor: "Aqua Co" });
    expect(applyLocationFilters(rows, f).length).toBeGreaterThan(0);
    expect(selectedCount(f)).toBeLessThan(4);
  });

  it("matches ignoring capital letters and spaces, so 'karnataka ' and 'Karnataka' are the same state", () => {
    const messy = [row("south", " karnataka ", "Mysuru", "Aqua Co"), row("South", "Karnataka", "Bengaluru", "Aqua Co")];
    expect(optionsFor(messy, NO_FILTERS, "state")).toHaveLength(1);
    expect(applyLocationFilters(messy, { ...NO_FILTERS, state: "Karnataka" })).toHaveLength(2);
  });
});

function selectedCount(f: Record<string, string>) {
  return Object.values(f).filter(Boolean).length;
}
