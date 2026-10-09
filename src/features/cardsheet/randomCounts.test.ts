import { describe, expect, it } from "vitest";
import { datesBetween, freshDistribution, randomDistribution } from "./randomCounts";

describe("random count distribution", () => {
  it("includes both ends, across months and a single day", () => {
    expect(datesBetween("2026-10-01", "2026-10-10")).toHaveLength(10);
    expect(datesBetween("2026-09-29", "2026-10-02")).toEqual(["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]);
    expect(datesBetween("2026-10-05", "2026-10-05")).toEqual(["2026-10-05"]);
  });

  it("always sums to the total with non-negative whole numbers", () => {
    for (const [total, n] of [[0, 5], [1, 10], [100, 10], [100, 1], [7, 31], [100000, 366]]) {
      const days = datesBetween("2026-01-01", new Date(Date.UTC(2026, 0, n)).toISOString().slice(0, 10));
      const rows = randomDistribution(total, days);
      expect(rows).toHaveLength(days.length);
      expect(rows.reduce((s, r) => s + r.count, 0)).toBe(total);
      expect(rows.every((r) => Number.isInteger(r.count) && r.count >= 0)).toBe(true);
    }
  });

  it("regenerate gives a different split", () => {
    const days = datesBetween("2026-10-01", "2026-10-10");
    const first = randomDistribution(100, days);
    for (let i = 0; i < 50; i++) {
      const next = freshDistribution(100, days, first);
      expect(next.map((r) => r.count)).not.toEqual(first.map((r) => r.count));
    }
  });

  it("without zero days every day gets at least 1 and the sum is still exact", () => {
    const days = datesBetween("2026-10-01", "2026-10-10");
    for (const total of [10, 11, 100]) {
      const rows = randomDistribution(total, days, false);
      expect(rows.reduce((s, r) => s + r.count, 0)).toBe(total);
      expect(rows.every((r) => r.count >= 1)).toBe(true);
    }
  });
});
