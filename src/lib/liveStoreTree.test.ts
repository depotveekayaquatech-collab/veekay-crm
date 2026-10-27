import { describe, expect, it } from "vitest";
import { buildTree, expandableIds, leafRows, levelsFor, summarize, visibleRows, type TreeSource } from "./liveStoreTree";

const store = (o: Partial<TreeSource>): TreeSource => ({
  platformSlug: "zepto", status: "LIVE", regionName: null, state: "Delhi", city: "New Delhi", vendorName: "V1", pendingDays: 0, markedToday: false, monthBottles: 0, ...o,
});

describe("buildTree", () => {
  it("groups Zepto by state then city and counts stores and distinct vendors", () => {
    const items = [
      store({ city: "Rohini", vendorName: "A" }), store({ city: "Rohini", vendorName: "a" }), store({ city: "Saket", vendorName: "B" }),
      store({ state: "Haryana", city: "Gurugram", vendorName: "A" }),
    ];
    const tree = buildTree(items, levelsFor("zepto"));
    expect(tree.map((n) => [n.label, n.stores, n.vendors])).toEqual([["Delhi", 3, 2], ["Haryana", 1, 1]]);      // "A" and "a" are one vendor
    expect(tree[0].children.map((c) => [c.label, c.stores, c.vendors])).toEqual([["Rohini", 2, 1], ["Saket", 1, 1]]);
  });

  it("groups Blinkit by region, then state, then city", () => {
    const items = [store({ platformSlug: "blinkit", regionName: "North" }), store({ platformSlug: "blinkit", regionName: "South", state: "Karnataka", city: "Bengaluru" })];
    const tree = buildTree(items, levelsFor("blinkit"));
    expect(tree.map((n) => n.label).sort()).toEqual(["North", "South"]);
    expect(tree[0].children[0].children[0].path.map((p) => p.level)).toEqual(["region", "state", "city"]);
  });

  it("counts only live stores", () => {
    const items = [store({}), store({ status: "PENDING" }), store({ status: "CLOSE" })];
    expect(buildTree(items, levelsFor("zepto"))[0].stores).toBe(1);
    expect(summarize(items).stores).toBe(1);
  });

  it("treats spellings that differ by case or spacing as one place, named the way most stores spell it", () => {
    const items = [store({ state: "DElhi" }), store({ state: "Delhi" }), store({ state: "delhi" }), store({ state: "Delhi " }), store({ state: "MAHARASHTRA" }), store({ state: "Maharashtra" }), store({ state: "Maharashtra" })];
    const tree = buildTree(items, ["state"]);
    expect(tree.map((n) => [n.label, n.stores])).toEqual([["Delhi", 4], ["Maharashtra", 3]]);
  });

  it("keeps a store with no value in its own 'Not set' group that cannot be filtered on", () => {
    const tree = buildTree([store({ state: null }), store({})], ["state"]);
    const unset = tree.find((n) => n.label === "Not set");
    expect(unset?.stores).toBe(1);
    expect(unset?.path).toEqual([{ level: "state", value: "" }]);
  });

  it("adds up behind, marked today and bottles, and sorts the biggest place first", () => {
    const items = [
      store({ state: "A", pendingDays: 2, monthBottles: 10 }), store({ state: "A", markedToday: true, monthBottles: 5 }),
      store({ state: "B", pendingDays: 0 }), store({ state: "B" }), store({ state: "B" }),
    ];
    const tree = buildTree(items, ["state"]);
    expect(tree.map((n) => n.label)).toEqual(["B", "A"]);
    const a = tree.find((n) => n.label === "A")!;
    expect([a.behind, a.markedToday, a.bottles]).toEqual([1, 1, 15]);
  });
});

describe("summarize, visibleRows, leafRows", () => {
  const items = [store({ city: "Rohini" }), store({ city: "Saket", vendorName: "B" }), store({ state: "Haryana", city: "Gurugram" })];

  it("totals states, cities and vendors", () => {
    expect(summarize(items)).toMatchObject({ stores: 3, vendors: 2, states: 2, cities: 3 });
  });

  it("shows children only while their parent is expanded", () => {
    const tree = buildTree(items, levelsFor("zepto"));
    expect(visibleRows(tree, new Set()).map((r) => r.node.label)).toEqual(["Delhi", "Haryana"]);
    expect(visibleRows(tree, new Set(expandableIds(tree))).map((r) => [r.node.label, r.depth])).toEqual([["Delhi", 0], ["Rohini", 1], ["Saket", 1], ["Haryana", 0], ["Gurugram", 1]]);
  });

  it("lists the deepest places for the CSV", () => {
    expect(leafRows(buildTree(items, levelsFor("zepto"))).map((n) => n.path.map((p) => p.value).join(" > "))).toEqual(["Delhi > Rohini", "Delhi > Saket", "Haryana > Gurugram"]);
  });
});
