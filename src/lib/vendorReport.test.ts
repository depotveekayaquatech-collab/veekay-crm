import { describe, expect, it } from "vitest";
import { formatVendor, formatVendorReport, type ReportVendor } from "./vendorReport";

const two: ReportVendor = {
  vendor_name: "Aqua Traders", bottles: 200,
  stores: [{ store_name: "Store One", external_code: "BLK-4821", bottles: 120 }, { store_name: "Store Two", external_code: "BLK-4830", bottles: 80 }],
};
const one: ReportVendor = { vendor_name: "Solo Co", bottles: 5, stores: [{ store_name: "Solo Store", external_code: "ZPT-17", bottles: 5 }] };

describe("vendor report text", () => {
  it("lists each store as 'name (outlet ID) - bottles' and a total when there are several", () => {
    expect(formatVendor(two)).toBe("Vendor name - Aqua Traders\nStore One (BLK-4821) - 120\nStore Two (BLK-4830) - 80\nTotal bottles - 200");
  });

  it("gives a one-store vendor just its store, with no total line", () => {
    expect(formatVendor(one)).toBe("Vendor name - Solo Co\nSolo Store (ZPT-17) - 5");
  });

  it("leaves the brackets out when a store has no outlet ID", () => {
    expect(formatVendor({ ...one, stores: [{ store_name: "Solo Store", external_code: "", bottles: 5 }] })).toBe("Vendor name - Solo Co\nSolo Store - 5");
  });

  it("groups thousands the Indian way and keeps a store with nothing marked", () => {
    const v: ReportVendor = { vendor_name: "Big", bottles: 123456, stores: [{ store_name: "A", external_code: "A1", bottles: 123456 }, { store_name: "B", external_code: "B1", bottles: 0 }] };
    expect(formatVendor(v)).toBe("Vendor name - Big\nA (A1) - 1,23,456\nB (B1) - 0\nTotal bottles - 1,23,456");
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
