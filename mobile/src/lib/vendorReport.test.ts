import test from "node:test";
import assert from "node:assert/strict";
import { formatVendor, formatVendorReport, type ReportVendor } from "./vendorReport.ts";

const two: ReportVendor = {
  vendor_name: "Aqua Traders", bottles: 200,
  stores: [{ store_name: "Store One", external_code: "BLK-4821", bottles: 120 }, { store_name: "Store Two", external_code: "BLK-4830", bottles: 80 }],
};
const one: ReportVendor = { vendor_name: "Solo Co", bottles: 5, stores: [{ store_name: "Solo Store", external_code: "ZPT-17", bottles: 5 }] };

test("lists each store as 'name (outlet ID) - bottles' and a total when there are several", () => {
  assert.equal(formatVendor(two), "Vendor name - Aqua Traders\nStore One (BLK-4821) - 120\nStore Two (BLK-4830) - 80\nTotal bottles - 200");
});

test("gives a one-store vendor just its store, with no total line", () => {
  assert.equal(formatVendor(one), "Vendor name - Solo Co\nSolo Store (ZPT-17) - 5");
});

test("leaves the brackets out when a store has no outlet ID", () => {
  assert.equal(formatVendor({ ...one, stores: [{ store_name: "Solo Store", external_code: "", bottles: 5 }] }), "Vendor name - Solo Co\nSolo Store - 5");
});

test("names a vendor with no name", () => {
  assert.equal(formatVendor({ ...one, vendor_name: null }).split("\n")[0], "Vendor name - (No vendor name)");
});

test("puts a heading, then a blank line between vendors", () => {
  const text = formatVendorReport("Blinkit - October 2026", [two, one]);
  assert.equal(text.split("\n")[0], "Blinkit - October 2026");
  assert.ok(text.includes("Total bottles - 200\n\nVendor name - Solo Co"));
});

test("is empty when there is nobody to report", () => {
  assert.equal(formatVendorReport("x", []), "");
});
