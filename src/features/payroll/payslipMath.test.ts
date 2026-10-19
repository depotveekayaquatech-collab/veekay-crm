import { describe, expect, it } from "vitest";
import type { PayDay } from "@/features/payroll/api";
import { countedWith, previewDays } from "@/features/payroll/payslipMath";

const day = (date: string, over: Partial<PayDay> = {}): PayDay => ({
  date, weekday: 0, kind: "PRESENT", mark: null, counted: 1, default: 1, checkInAt: null, checkOutAt: null, minutes: 0,
  late: false, noCheckout: false, location: null, leaveType: null, halfDay: false, ...over,
});

describe("payslip preview", () => {
  const days = [day("2026-09-01"), day("2026-09-02", { kind: "ABSENT", counted: 0, default: 0 }), day("2026-09-03", { mark: "HALF", counted: 0.5 })];

  it("uses what is saved when nothing is pending", () => {
    expect(previewDays(days, {})).toBe(1.5);
  });

  it("applies a pending mark, and AUTO goes back to the default", () => {
    expect(countedWith(days[0], { "2026-09-01": "HALF" })).toBe(0.5);
    expect(countedWith(days[1], { "2026-09-02": "FULL" })).toBe(1);
    expect(countedWith(days[2], { "2026-09-03": "AUTO" })).toBe(1);
    expect(previewDays(days, { "2026-09-01": "ABSENT", "2026-09-02": "FULL" })).toBe(1.5);
  });
});
