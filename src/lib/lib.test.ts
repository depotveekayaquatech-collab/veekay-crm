import { describe, expect, it } from "vitest";
import { camelize } from "./camel";
import { complianceMonths, monthLabel, recentMonths } from "./months";
import { fmtMinutes } from "@/features/attendance/format";

describe("camelize", () => {
  it("converts keys deeply and leaves values alone", () => {
    expect(camelize({ store_name: "a_b", rows: [{ this_month_bottles: 3 }], n: null })).toEqual({
      storeName: "a_b",
      rows: [{ thisMonthBottles: 3 }],
      n: null,
    });
  });
});

describe("months", () => {
  it("labels a month", () => {
    expect(monthLabel("2026-09")).toBe("September 2026");
    expect(monthLabel("junk")).toBe("junk");
  });
  it("compliance months run newest first, never before 2026-06, at most 13 entries", () => {
    const m = complianceMonths(new Date(2026, 9, 15));
    expect(m[0]).toBe("2026-10");
    expect(m[m.length - 1]).toBe("2026-06");
    expect(complianceMonths(new Date(2030, 0, 1)).length).toBe(13);
  });
  it("recentMonths crosses a year boundary", () => {
    expect(recentMonths(3, new Date(2027, 0, 5))).toEqual(["2027-01", "2026-12", "2026-11"]);
  });
});

describe("fmtMinutes", () => {
  it.each([
    [0, "0m"],
    [45, "45m"],
    [60, "1h"],
    [135, "2h 15m"],
  ])("%i -> %s", (m, out) => expect(fmtMinutes(m)).toBe(out));
});
