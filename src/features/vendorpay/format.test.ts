import { describe, expect, it } from "vitest";
import { inr } from "@/features/cash/api";
import { ageText, currentMonthIst, isMonth, monthOptions, shiftMonth, vendorLabel } from "./format";

describe("Indian amounts", () => {
  it("groups digits the Indian way with two decimals", () => {
    expect(inr("123456")).toBe("₹1,23,456.00");
    expect(inr("1234567.5")).toBe("₹12,34,567.50");
    expect(inr("0")).toBe("₹0.00");
    expect(inr("-3000")).toBe("-₹3,000.00");
  });
});

describe("months", () => {
  it("reads this month on the India clock, not the browser's", () => {
    expect(currentMonthIst(new Date("2026-10-31T18:00:00Z"))).toBe("2026-10"); // 23:30 on 31 Oct in India
    expect(currentMonthIst(new Date("2026-10-31T18:31:00Z"))).toBe("2026-11"); // 00:01 on 1 Nov in India
    expect(currentMonthIst(new Date("2026-12-31T20:00:00Z"))).toBe("2027-01");
  });

  it("shifts across year ends", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-10", -11)).toBe("2025-11");
  });

  it("offers newest first and keeps an older selection", () => {
    const options = monthOptions("2026-11", "2026-11", 3);
    expect(options.map((o) => o.value)).toEqual(["2026-11", "2026-10", "2026-09"]);
    expect(options[0].label).toBe("November 2026");
    expect(monthOptions("2026-11", "2020-01", 3).at(-1)?.value).toBe("2020-01");
  });

  it("validates the month in the address bar", () => {
    expect(isMonth("2026-10")).toBe(true);
    expect(["2026-13", "2026-1", "junk", "", null, undefined].some(isMonth)).toBe(false);
  });
});

describe("labels", () => {
  it("shows name, city and code so a search finds any of them", () => {
    expect(vendorLabel({ vendorCode: "V0123", name: "Sharma Traders", city: "Gurugram" })).toBe("Sharma Traders, Gurugram (V0123)");
    expect(vendorLabel({ vendorCode: "V0124", name: "No City", city: null })).toBe("No City (V0124)");
  });

  it("describes how old the data is", () => {
    expect(ageText(0)).toBe("just now");
    expect(ageText(1)).toBe("1 minute ago");
    expect(ageText(125)).toBe("2 hours ago");
    expect(ageText(60 * 72)).toBe("3 days ago");
  });
});
