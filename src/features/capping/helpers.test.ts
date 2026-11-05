import { describe, expect, it } from "vitest";
import { dateLabel, dayLabel, fmtAvg, istToday, monthRange, recentMonths } from "./helpers";

describe("capping dates (Asia/Kolkata)", () => {
  it("takes the day from India, not from the browser's zone", () => {
    expect(istToday(new Date("2026-10-26T19:00:00Z"))).toBe("2026-10-27");     // 00:30 on the 27th in India
    expect(istToday(new Date("2026-10-26T17:00:00Z"))).toBe("2026-10-26");     // 22:30 on the 26th in India
  });
  it("labels dates", () => {
    expect(dayLabel("2026-10-01")).toBe("01-Oct");
    expect(dateLabel("2026-12-15")).toBe("15-Dec-2026");
  });
  it("always shows two decimals", () => {
    expect(fmtAvg(9.4)).toBe("9.40");
    expect(fmtAvg(11)).toBe("11.00");
    expect(fmtAvg(9.333)).toBe("9.33");
    expect(fmtAvg(null)).toBe("—");
  });
});

describe("capping months", () => {
  it("lists the last twelve months, this one first, across a year end", () => {
    const m = recentMonths("2026-02-10");
    expect(m).toHaveLength(12);
    expect(m.slice(0, 3)).toEqual(["2026-02", "2026-01", "2025-12"]);
    expect(m[11]).toBe("2025-03");
  });
  it("asks the alert for the whole of a finished month and only up to today for this one", () => {
    expect(monthRange("2026-10", "2026-11-05")).toEqual({ from: "2026-10-01", to: "2026-10-31" });
    expect(monthRange("2026-11", "2026-11-05")).toEqual({ from: "2026-11-01", to: "2026-11-05" });
    expect(monthRange("2028-02", "2028-03-01")).toEqual({ from: "2028-02-01", to: "2028-02-29" });
  });
});
