import test from "node:test";
import assert from "node:assert/strict";
import { chipCounts, groupByVendor, matchesSearch, ordersPending, passesFilter, pendingText, phonesOf, type DocFlags, type InvStore } from "./inventory.ts";

const store = (o: Partial<InvStore> & { id: string }): InvStore => ({
  name: `Store ${o.id}`, external_code: `X-${o.id}`, city: "Jaipur", state: "Rajasthan", region_name: "WEST", vendor_name: "Shyam RO", today_count: null, ...o,
});
const docs = (entries: Record<string, DocFlags>) => new Map(Object.entries(entries));

test("stores are grouped by vendor, spelled with any case or spacing, A to Z with no-vendor last", () => {
  const g = groupByVendor([
    store({ id: "1", vendor_name: "SHYAM  RO" }), store({ id: "2", vendor_name: "shyam ro" }), store({ id: "3", vendor_name: "Aman" }), store({ id: "4", vendor_name: null }),
  ], new Map());
  assert.deepEqual(g.map((x) => [x.name, x.stores.length]), [["Aman", 1], ["SHYAM RO", 2], ["No vendor", 1]]);
});

test("a vendor's phone numbers are its distinct numbers, a store sheet's 'a / b' split, repeats and spacing ignored", () => {
  assert.deepEqual(phonesOf([
    store({ id: "1", vendor_number: "9828069773 / 9351017595" }), store({ id: "2", vendor_number: "98280 69773" }), store({ id: "3", vendor_number: null }), store({ id: "4", vendor_number: "" }),
  ]), ["9828069773", "9351017595"]);
});

test("each vendor counts the stores that have the month's card and bill; an unknown store counts for neither", () => {
  const stores = [store({ id: "1" }), store({ id: "2" }), store({ id: "3" })];
  const [g] = groupByVendor(stores, docs({ "1": { card: true, bill: false }, "2": { card: true, bill: true } }));
  assert.equal(g.cards, 2);
  assert.equal(g.bills, 1);
});

test("the filters: missing card, missing bill and orders still to mark today", () => {
  const a = store({ id: "a", today_marked: true, today_count: 5 });
  const b = store({ id: "b", today_marked: false });
  const c = store({ id: "c" });                                              // no document information at all
  const map = docs({ a: { card: true, bill: false }, b: { card: false, bill: true } });
  assert.deepEqual([a, b, c].filter((s) => passesFilter(s, map, "card")).map((s) => s.id), ["b"]);
  assert.deepEqual([a, b, c].filter((s) => passesFilter(s, map, "bill")).map((s) => s.id), ["a"]);
  assert.deepEqual([a, b, c].filter((s) => passesFilter(s, map, "orders")).map((s) => s.id), ["b", "c"]);
  assert.deepEqual(chipCounts([a, b, c], map), { all: 3, card: 1, bill: 1, orders: 2 });
});

test("orders are pending until somebody marked today, whoever's number it is", () => {
  assert.equal(ordersPending(store({ id: "1", today_count: null })), true);
  assert.equal(ordersPending(store({ id: "1", today_count: 7 })), false);
  assert.equal(ordersPending(store({ id: "1", today_count: null, today_marked: true })), false);      // a colleague marked it
});

test("search looks at the store, its code, city, vendor and POC", () => {
  const s = store({ id: "1", name: "CPC-JAI1", external_code: "CPC JAI1", poc_name: "Avinash saini" });
  for (const q of ["jai1", "cpc jai", "jaipur", "shyam", "avinash", "  "]) assert.equal(matchesSearch(s, q), true, q);
  assert.equal(matchesSearch(s, "mumbai"), false);
});

test("the pending banner", () => {
  assert.equal(pendingText(3), "3 days pending");
  assert.equal(pendingText(1), "1 day pending");
  assert.equal(pendingText(0), "All up to date");
  assert.equal(pendingText(undefined), "All up to date");
});
