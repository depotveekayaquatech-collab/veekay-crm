import { describe, expect, it } from "vitest";
import { dateLabel, dayLabel, isBackdated, istToday } from "./helpers";

describe("capping dates (Asia/Kolkata)", () => {
  it("takes the day from India, not from the browser's zone", () => {
    expect(istToday(new Date("2026-10-26T19:00:00Z"))).toBe("2026-10-27");     // 00:30 on the 27th in India
    expect(istToday(new Date("2026-10-26T17:00:00Z"))).toBe("2026-10-26");     // 22:30 on the 26th in India
  });
  it("labels dates", () => {
    expect(dayLabel("2026-10-01")).toBe("01-Oct");
    expect(dateLabel("2026-12-15")).toBe("15-Dec-2026");
  });
  it("treats only an earlier day as backdated", () => {
    expect(isBackdated("2026-10-26", "2026-10-27")).toBe(true);
    expect(isBackdated("2026-10-27", "2026-10-27")).toBe(false);
  });
});
