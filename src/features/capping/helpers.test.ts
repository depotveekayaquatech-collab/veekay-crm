import { describe, expect, it } from "vitest";
import { alertReasons, currentMonth, dateLabel, dayLabel, fmtAvg, isBackdated, istToday, monthRange, periodToDate } from "./helpers";

describe("capping dates (Asia/Kolkata)", () => {
  it("takes the day from India, not from the browser's zone", () => {
    expect(istToday(new Date("2026-10-26T19:00:00Z"))).toBe("2026-10-27");     // 00:30 on the 27th in India
    expect(istToday(new Date("2026-10-26T17:00:00Z"))).toBe("2026-10-26");     // 22:30 on the 26th in India
    expect(currentMonth(new Date("2026-10-31T19:00:00Z"))).toBe("2026-11");
  });
  it("gives the first and last day of a month", () => {
    expect(monthRange("2026-10")).toEqual({ from: "2026-10-01", to: "2026-10-31" });
    expect(monthRange("2026-02")).toEqual({ from: "2026-02-01", to: "2026-02-28" });
    expect(monthRange("2028-02").to).toBe("2028-02-29");
  });
  it("averages run from the 1st to today for this month and the whole month for a finished one", () => {
    expect(periodToDate("2026-10", "2026-10-27")).toEqual({ from: "2026-10-01", to: "2026-10-27" });
    expect(periodToDate("2026-10", "2026-10-31")).toEqual({ from: "2026-10-01", to: "2026-10-31" });
    expect(periodToDate("2026-09", "2026-10-27")).toEqual({ from: "2026-09-01", to: "2026-09-30" });
  });
  it("labels dates like the downloaded sheet", () => {
    expect(dayLabel("2026-10-01")).toBe("01-Oct");
    expect(dateLabel("2026-12-15")).toBe("15-Dec-2026");
  });
  it("treats only an earlier day as backdated", () => {
    expect(isBackdated("2026-10-26", "2026-10-27")).toBe(true);
    expect(isBackdated("2026-10-27", "2026-10-27")).toBe(false);
  });
});

describe("alertReasons", () => {
  it("names the average and the days, and folds a long list", () => {
    const row = { averageBreach: true, average: 12.5, breachDays: [{ date: "2026-10-02", value: 13 }, { date: "2026-10-03", value: 12 }] };
    expect(alertReasons(row)).toEqual(["entry average 12.50", "13 on 02-Oct", "12 on 03-Oct"]);
    const many = { averageBreach: false, average: 9, breachDays: [1, 2, 3, 4, 5].map((d) => ({ date: `2026-10-0${d}`, value: 12 })) };
    expect(alertReasons(many)).toEqual(["12 on 01-Oct", "12 on 02-Oct", "12 on 03-Oct", "+2 more days"]);
    expect(alertReasons({ averageBreach: false, average: 5, breachDays: [] })).toEqual([]);
  });
  it("names the capping average too", () => {
    expect(alertReasons({ averageBreach: false, average: 9, cappingBreach: true, cappingAverage: 11.5, breachDays: [] })).toEqual(["capping average 11.50"]);
  });
  it("always shows two decimals", () => {
    expect(fmtAvg(9.4)).toBe("9.40");
    expect(fmtAvg(11)).toBe("11.00");
    expect(fmtAvg(9.333)).toBe("9.33");
    expect(fmtAvg(null)).toBe("—");
  });
});
