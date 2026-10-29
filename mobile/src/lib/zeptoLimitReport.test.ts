import test from "node:test";
import assert from "node:assert/strict";
import { formatLimitReport, formatLimitStore, formatLimitVendor, type LimitVendor } from "./zeptoLimitReport.ts";

const two: LimitVendor = {
  vendor_name: "Aqua Traders",
  stores: [
    { store_name: "Store One", external_code: "ZPT-1", monthly_limit: 900, bottles: 450, pending: 450 },
    { store_name: "Store Two", external_code: "ZPT-2", monthly_limit: 600, bottles: 100, pending: 500 },
  ],
};

test("gives a store its limit, what was supplied and what is pending", () => {
  assert.equal(formatLimitStore(two.stores[0]), "Store - Store One (ZPT-1)\nMonthly limit - 900\nSupplied till date - 450\nPending limit - 450");
});

test("stops the pending limit at 0 and says by how much a store went over", () => {
  assert.equal(formatLimitStore({ store_name: "A", monthly_limit: 60, bottles: 70, pending: 0, over_by: 10 }), "Store - A\nMonthly limit - 60\nSupplied till date - 70\nPending limit - 0 (over by 10)");
});

test("shows only the supplied bottles for a store with no capping", () => {
  assert.equal(formatLimitStore({ store_name: "A", monthly_limit: null, bottles: 5, pending: null }), "Store - A\nMonthly limit - No capping set\nSupplied till date - 5");
});

test("adds a total only when the vendor has several stores with a limit", () => {
  assert.ok(formatLimitVendor(two).includes("Total of 2 stores\nMonthly limit - 1,500\nSupplied till date - 550\nPending limit - 950"));
  assert.ok(!formatLimitVendor({ vendor_name: "Solo", stores: [two.stores[0]] }).includes("Total"));
});

test("puts a heading first and is empty with nobody to report", () => {
  assert.equal(formatLimitReport("Zepto - October 2026", [two]).split("\n")[0], "Zepto - October 2026");
  assert.equal(formatLimitReport("x", []), "");
});
