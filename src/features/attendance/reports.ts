import { fmtTime, locationText, presenceText } from "@/features/attendance/format";
import type { DayEntry, DayOverview, DayRow, DayStatus, MonthData, MonthRow } from "@/features/attendance/api";

export interface CsvTable {
  header: string[];
  rows: (string | number)[][];
}

const WEEKLY_OFF_WEEKDAY = 0; // Sunday, as Date.getDay() counts it
const DAY_NAME = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** The plain word for a day's status; every kind of "present" reads the same. */
export function statusWord(status: DayStatus): string {
  if (status === "ON_LEAVE") return "On leave";
  if (status === "OFF") return "Day off";
  if (status === "ABSENT") return "Absent";
  return "Present";
}

function weekday(iso: string): number {
  return new Date(`${iso}T12:00:00`).getDay();
}

/** One day of one person in the plain report: P present, P½ half day, L leave, A absent, H holiday, WO weekly off, blank when there is nothing to say (future, or before they joined). */
export function dayCode(row: MonthRow, date: string, holidays: MonthData["holidays"]): string {
  const e = row.days[date];
  if (e) return e.status === "ON_LEAVE" ? "L" : e.halfDay ? "P½" : "P";
  if (holidays?.[date]) return "H";
  if (weekday(date) === WEEKLY_OFF_WEEKDAY) return "WO";
  return row.absentDates.includes(date) ? "A" : "";
}

/** Plain monthly report: one row per person, one column per date, with P / A / L / H / WO. */
export function monthlySummary(data: MonthData, rows: MonthRow[]): CsvTable {
  return {
    header: ["Employee ID", "Name", "Platform", "Days present", "Leave", "Absent", "Late", ...data.dates.map((d) => d.slice(8))],
    rows: rows.map((r) => [
      r.employeeCode, r.fullName, r.platform ?? "", r.daysPresent, r.leaveDays, r.absentDays, r.lateDays,
      ...data.dates.map((d) => dayCode(r, d, data.holidays)),
    ]),
  };
}

function entryWhere(e: DayEntry): string {
  if (!e.checkInAt) return e.location.label; // marked from a sheet or by a developer: no position was recorded
  return [presenceText(e.location), locationText(e.location)].filter(Boolean).join(" - ");
}

function entryStatus(e: DayEntry): string {
  if (e.status === "CHECKED_IN") return "Present (still in)";
  if (e.status === "NO_CHECKOUT") return "Present (no check-out)";
  return statusWord(e.status);
}

/** Detailed monthly report: one row per person per date with the status and the times. Future days and days before the person joined are left out. */
export function monthlyDetailed(data: MonthData, rows: MonthRow[]): CsvTable {
  const out: (string | number)[][] = [];
  for (const r of rows) {
    for (const d of data.dates) {
      const code = dayCode(r, d, data.holidays);
      if (!code) continue;
      const base = [r.employeeCode, r.fullName, r.platform ?? "", d, DAY_NAME[weekday(d)]];
      const e = r.days[d];
      if (e) {
        const timed = Boolean(e.checkInAt);
        out.push([
          ...base, e.status === "ON_LEAVE" ? "On leave" : entryStatus(e),
          timed ? fmtTime(e.checkInAt) : "", timed && e.checkOutAt ? fmtTime(e.checkOutAt) : "", timed ? (e.minutes / 60).toFixed(2) : "",
          e.late ? "Yes" : "", e.halfDay ? "Yes" : "", e.status === "ON_LEAVE" ? "" : entryWhere(e),
        ]);
      } else {
        out.push([...base, code === "A" ? "Absent" : code === "H" ? `Holiday: ${data.holidays?.[d] ?? ""}` : "Weekly off", "", "", "", "", "", ""]);
      }
    }
  }
  return { header: ["Employee ID", "Name", "Platform", "Date", "Day", "Status", "Check in", "Check out", "Hours", "Late", "Half day", "Where"], rows: out };
}

/** Plain report for one day: who was present, absent, on leave. */
export function dailySummary(data: DayOverview, rows: DayRow[]): CsvTable {
  return {
    header: ["Date", "Employee ID", "Name", "Role", "Platform", "Status", "Late"],
    rows: rows.map((r) => [data.date, r.employeeCode, r.fullName, r.roles.join("/"), r.platform ?? "", statusWord(r.status), r.late ? "Yes" : ""]),
  };
}

/** Detailed report for one day: the plain columns plus check-in / check-out times, hours and where they checked in from. */
export function dailyDetailed(data: DayOverview, rows: DayRow[]): CsvTable {
  return {
    header: ["Date", "Employee ID", "Name", "Role", "Platform", "Status", "Late", "Check in", "Check out", "Hours", "Check-in presence", "Check-in location", "Latitude", "Longitude", "Distance to office (m)", "Check-out presence", "Check-out location"],
    rows: rows.map((r) => [
      data.date, r.employeeCode, r.fullName, r.roles.join("/"), r.platform ?? "", statusWord(r.status), r.late ? "Yes" : "",
      r.checkInAt ? fmtTime(r.checkInAt) : "", r.checkOutAt ? fmtTime(r.checkOutAt) : "", r.checkInAt ? (r.minutes / 60).toFixed(2) : "",
      presenceText(r.checkInAt ? r.location : null), r.checkInAt ? locationText(r.location) : r.status === "PRESENT" ? r.location.label : "",
      r.location.latitude ?? "", r.location.longitude ?? "", r.location.distanceM ?? "",
      presenceText(r.checkOutAt ? r.checkOutLocation : null), locationText(r.checkOutAt ? r.checkOutLocation : null),
    ]),
  };
}
