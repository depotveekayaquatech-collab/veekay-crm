import { describe, expect, it } from "vitest";
import { dayCode, monthlyDetailed, monthlySummary } from "@/features/attendance/reports";
import type { DayEntry, MonthData, MonthRow } from "@/features/attendance/api";

const office = { status: "office" as const, label: "Head Office" };
const real: DayEntry = { status: "CHECKED_OUT", checkInAt: "2026-10-05T04:30:00Z", checkOutAt: "2026-10-05T12:30:00Z", minutes: 480, late: true, location: office };
const sheet: DayEntry = { status: "PRESENT", checkInAt: null, checkOutAt: null, minutes: 0, late: false, location: { status: "unknown", label: "Attendance sheet" } };
const leave: DayEntry = { status: "ON_LEAVE", checkInAt: null, checkOutAt: null, minutes: 0, late: false, location: { status: "unknown", label: "—" } };

// 2026-10-04 is a Sunday; the 5th is checked in, the 6th is from a sheet, the 7th is leave, the 8th is absent, the 9th a holiday, the 10th before joining
const row = {
  userId: "u1", employeeCode: "E1", fullName: "Asha", platform: "zepto", daysPresent: 2, leaveDays: 1, absentDays: 1, lateDays: 1, absentDates: ["2026-10-08"],
  days: { "2026-10-05": real, "2026-10-06": sheet, "2026-10-07": leave },
} as unknown as MonthRow;
const data = { month: "2026-10", dates: ["2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10"], today: "2026-10-20", holidays: { "2026-10-09": "Diwali" }, rows: [row] } as unknown as MonthData;

describe("attendance reports", () => {
  it("codes each day as present, leave, absent, holiday or weekly off", () => {
    expect(data.dates.map((d) => dayCode(row, d, data.holidays))).toEqual(["WO", "P", "P", "L", "A", "H", ""]);
  });

  it("the plain report has the codes and no times", () => {
    const { header, rows } = monthlySummary(data, [row]);
    expect(header.slice(0, 7)).toEqual(["Employee ID", "Name", "Platform", "Days present", "Leave", "Absent", "Late"]);
    expect(rows[0].slice(7)).toEqual(["WO", "P", "P", "L", "A", "H", ""]);
    expect(header).not.toContain("Check in");
  });

  it("the detailed report has the status and the times of every day", () => {
    const { header, rows } = monthlyDetailed(data, [row]);
    const col = (name: string) => header.indexOf(name);
    const byDate = Object.fromEntries(rows.map((r) => [r[col("Date")], r]));
    expect(rows).toHaveLength(6); // the day before joining is left out
    expect(byDate["2026-10-05"][col("Status")]).toBe("Present");
    expect(byDate["2026-10-05"][col("Check in")]).not.toBe("");
    expect(byDate["2026-10-05"][col("Hours")]).toBe("8.00");
    expect(byDate["2026-10-05"][col("Late")]).toBe("Yes");
    expect(byDate["2026-10-06"][col("Status")]).toBe("Present"); // from a sheet: present, no invented times
    expect(byDate["2026-10-06"][col("Check in")]).toBe("");
    expect(byDate["2026-10-06"][col("Where")]).toBe("Attendance sheet");
    expect(byDate["2026-10-07"][col("Status")]).toBe("On leave");
    expect(byDate["2026-10-08"][col("Status")]).toBe("Absent");
    expect(byDate["2026-10-09"][col("Status")]).toBe("Holiday: Diwali");
    expect(byDate["2026-10-04"][col("Status")]).toBe("Weekly off");
  });
});
