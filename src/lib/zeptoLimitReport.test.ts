import { describe, expect, it } from "vitest";
import { formatLimitReport, formatLimitStore, formatLimitVendor, groupByVendor, type LimitVendor } from "./zeptoLimitReport";

const two: LimitVendor = {
  vendor_name: "Aqua Traders",
  stores: [
    { store_name: "Store One", external_code: "ZPT-1", monthly_limit: 900, bottles: 450, pending: 450 },
    { store_name: "Store Two", external_code: "ZPT-2", monthly_limit: 600, bottles: 100, pending: 500 },
  ],
};

describe("Zepto vendor limit message", () => {
  it("gives a store its limit, what was supplied and what is pending", () => {
    expect(formatLimitStore(two.stores[0])).toBe("Store - Store One (ZPT-1)\nMonthly limit - 900\nSupplied till date - 450\nPending limit - 450");
  });

  it("stops the pending limit at 0 and says by how much a store went over", () => {
    expect(formatLimitStore({ store_name: "A", monthly_limit: 60, bottles: 70, pending: 0, over_by: 10 })).toBe("Store - A\nMonthly limit - 60\nSupplied till date - 70\nPending limit - 0 (over by 10)");
  });

  it("shows only the supplied bottles for a store with no capping", () => {
    expect(formatLimitStore({ store_name: "A", external_code: "", monthly_limit: null, bottles: 5, pending: null })).toBe("Store - A\nMonthly limit - No capping set\nSupplied till date - 5");
  });

  it("adds a total only when the vendor has several stores with a limit", () => {
    expect(formatLimitVendor(two)).toContain("Total of 2 stores\nMonthly limit - 1,500\nSupplied till date - 550\nPending limit - 950");
    expect(formatLimitVendor({ vendor_name: "Solo", stores: [two.stores[0]] })).not.toContain("Total");
    expect(formatLimitVendor({ vendor_name: null, stores: [two.stores[0]] }).split("\n")[0]).toBe("Vendor name - (No vendor name)");
  });

  it("does not count a store with no capping in the total", () => {
    const v: LimitVendor = { vendor_name: "V", stores: [...two.stores, { store_name: "C", monthly_limit: null, bottles: 9, pending: null }] };
    expect(formatLimitVendor(v)).toContain("Supplied till date - 550\nPending limit - 950");
  });

  it("puts a heading first and is empty with nobody to report", () => {
    expect(formatLimitReport("Zepto - October 2026", [two]).split("\n")[0]).toBe("Zepto - October 2026");
    expect(formatLimitReport("x", [])).toBe("");
  });

  it("groups stores by vendor, ignoring spelling and spacing, vendor-less last", () => {
    const row = (vendor_name: string | null, store_name: string) => ({ vendor_name, store_name, monthly_limit: 1, bottles: 0, pending: 1 });
    const got = groupByVendor([row("zed  aqua", "B"), row(null, "Z"), row("Zed Aqua", "A"), row("Alpha", "C")]);
    expect(got.map((g) => [g.vendor_name, g.stores.map((s) => s.store_name)])).toEqual([["Alpha", ["C"]], ["zed aqua", ["A", "B"]], [null, ["Z"]]]);
  });
});
