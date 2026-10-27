import { describe, expect, it } from "vitest";
import { formatVendor, formatVendorReport, type ReportVendor } from "./vendorReport";

const two: ReportVendor = { vendor_name: "Aqua Traders", bottles: 200, stores: [{ store_name: "Store One", bottles: 120 }, { store_name: "Store Two", bottles: 80 }] };
const one: ReportVendor = { vendor_name: "Solo Co", bottles: 5, stores: [{ store_name: "Solo Store", bottles: 5 }] };

describe("vendor report text", () => {
  it("lists each store as 'name - bottles' and a total when there are several", () => {
    expect(formatVendor(two)).toBe("Vendor name - Aqua Traders\nStore One - 120\nStore Two - 80\nTotal bottles - 200");
  });

  it("gives a one-store vendor just its store, with no total line", () => {
    expect(formatVendor(one)).toBe("Vendor name - Solo Co\nSolo Store - 5");
  });

  it("groups thousands the Indian way and keeps a store with nothing marked", () => {
    const v: ReportVendor = { vendor_name: "Big", bottles: 123456, stores: [{ store_name: "A", bottles: 123456 }, { store_name: "B", bottles: 0 }] };
    expect(formatVendor(v)).toBe("Vendor name - Big\nA - 1,23,456\nB - 0\nTotal bottles - 1,23,456");
  });

  it("names a vendor with no name", () => {
    expect(formatVendor({ ...one, vendor_name: null }).split("\n")[0]).toBe("Vendor name - (No vendor name)");
  });

  it("puts a heading, then a blank line between vendors", () => {
    const text = formatVendorReport("Blinkit - October 2026", [two, one]);
    expect(text.split("\n")[0]).toBe("Blinkit - October 2026");
    expect(text).toContain("Total bottles - 200\n\nVendor name - Solo Co");
  });

  it("is empty when there is nobody to report", () => {
    expect(formatVendorReport("x", [])).toBe("");
  });
});
