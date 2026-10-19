import { describe, expect, it } from "vitest";
import { summarizeByCity, type SummarySource } from "@/lib/regionSummary";

const s = (platformSlug: string, regionName: string | null, state: string | null, city: string | null, vendorName: string | null): SummarySource => ({ platformSlug, regionName, state, city, vendorName });
const items = [
  s("blinkit", "North", "Delhi", "New Delhi", "Aqua Co"),
  s("blinkit", "North", "Delhi", "New Delhi", "Aqua Co"),
  s("blinkit", "North", "Delhi", "New Delhi", "Pure Ltd"),
  s("blinkit", "North", "Haryana", "Gurugram", "Pure Ltd"),
  s("blinkit", "South", "Karnataka", "Bengaluru", "Aqua Co"),
  s("blinkit", "South", "Karnataka", "Bengaluru", "Clear Water"),
  s("blinkit", "South", "Karnataka", "Mysuru", "Aqua Co"),
  s("blinkit", "EAST", "West Bengal", "Kolkata", "Aqua Co"),   // other region: left out
  s("zepto", "North", "Delhi", "New Delhi", "Zep Vendor"),     // other platform: left out
];
const opts = { platformSlug: "blinkit", regions: ["North", "South"] };

describe("Blinkit region / state / city summary", () => {
  it("counts stores and DIFFERENT vendors per city", () => {
    const { rows } = summarizeByCity(items, opts);
    expect(rows.find((r) => r.city === "New Delhi")).toMatchObject({ vendors: 2, stores: 3 });     // Aqua Co twice counts once
    expect(rows.find((r) => r.city === "Bengaluru")).toMatchObject({ vendors: 2, stores: 2 });
    expect(rows.find((r) => r.city === "Mysuru")).toMatchObject({ vendors: 1, stores: 1 });
  });

  it("only includes the chosen platform and the chosen regions", () => {
    const { rows, total } = summarizeByCity(items, opts);
    expect(rows.map((r) => r.city)).not.toContain("Kolkata");
    expect(total.stores).toBe(7);
    expect(rows.reduce((n, r) => n + r.stores, 0)).toBe(7);
  });

  it("lists North before South, then states and cities A to Z", () => {
    const { rows, regions } = summarizeByCity(items, opts);
    expect(rows.map((r) => `${r.region}/${r.state}/${r.city}`)).toEqual([
      "North/Delhi/New Delhi", "North/Haryana/Gurugram", "South/Karnataka/Bengaluru", "South/Karnataka/Mysuru",
    ]);
    expect(regions.map((r) => r.region)).toEqual(["North", "South"]);
  });

  it("a vendor working in two cities counts once in the region and once overall, not once per city", () => {
    const { regions, total } = summarizeByCity(items, opts);
    expect(regions.find((r) => r.region === "North")).toMatchObject({ vendors: 2, stores: 4 });   // Aqua Co + Pure Ltd
    expect(regions.find((r) => r.region === "South")).toMatchObject({ vendors: 2, stores: 3 });   // Aqua Co + Clear Water
    expect(total.vendors).toBe(3);                                                                // Aqua Co is in both regions
  });

  it("keeps a store with no state, city or vendor instead of losing it, and ignores capitals and spaces", () => {
    const { rows, total } = summarizeByCity(
      [s("blinkit", "north ", null, null, null), s("blinkit", "North", " delhi", "NEW DELHI ", "Aqua"), s("blinkit", "North", "Delhi", "New Delhi", "aqua ")],
      opts,
    );
    expect(rows).toHaveLength(2);
    expect(rows.find((r) => r.city === "Not set")).toMatchObject({ state: "Not set", vendors: 0, stores: 1 });
    expect(rows.find((r) => r.city.toLowerCase().includes("delhi"))).toMatchObject({ vendors: 1, stores: 2 });
    expect(total.stores).toBe(3);
  });

  it("returns nothing for a platform with no stores", () => {
    expect(summarizeByCity(items, { platformSlug: "swiggy", regions: ["North"] })).toEqual({ rows: [], regions: [], total: { vendors: 0, stores: 0 } });
  });
});
