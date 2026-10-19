import { MARK_VALUE, type PayDay, type PayMark } from "@/features/payroll/api";

/** The admin's unsaved choice per date: a mark, or AUTO to take the mark away. */
export type Pending = Record<string, PayMark | "AUTO">;

/** What a day counts for once the pending (unsaved) choice is applied. */
export function countedWith(d: PayDay, pending: Pending | undefined): number {
  const p = pending?.[d.date];
  if (p === undefined) return d.counted;
  return p === "AUTO" ? d.default : MARK_VALUE[p];
}

export function previewDays(days: PayDay[], pending: Pending): number {
  return days.reduce((sum, d) => sum + countedWith(d, pending), 0);
}
