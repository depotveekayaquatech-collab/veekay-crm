import type { CapSummaryRow } from "@/services/capping";

/** Every date on the capping pages is an Asia/Kolkata day, whatever the browser's own time zone is. */
const IST = "Asia/Kolkata";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Today as YYYY-MM-DD in India. */
export function istToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** This month as YYYY-MM in India. */
export function currentMonth(now: Date = new Date()): string {
  return istToday(now).slice(0, 7);
}

/** First and last day of "YYYY-MM". */
export function monthRange(ym: string): { from: string; to: string } {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return { from: `${ym}-01`, to: `${ym}-${String(last).padStart(2, "0")}` };
}

/** "2026-10-01" -> "01-Oct" (the sheet's column header). */
export function dayLabel(iso: string): string {
  return `${iso.slice(8, 10)}-${MONTHS[Number(iso.slice(5, 7)) - 1]}`;
}

/** "2026-10-01" -> "01-Oct-2026". */
export function dateLabel(iso: string): string {
  return `${dayLabel(iso)}-${iso.slice(0, 4)}`;
}

/** A change dated before today asks for a confirmation first. */
export function isBackdated(effectiveFrom: string, today: string = istToday()): boolean {
  return effectiveFrom < today;
}

/** An average with exactly two decimals ("9.40"); a dash when there is none. */
export function fmtAvg(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

/** Why a store is in alert, in a few words: "entry average 12.50", "capping average 11.50", "13 on 02-Oct". Empty for a store that is not. */
export function alertReasons(
  row: Pick<CapSummaryRow, "averageBreach" | "average" | "breachDays"> & Partial<Pick<CapSummaryRow, "cappingBreach" | "cappingAverage">>,
  maxDays = 3,
): string[] {
  const out: string[] = [];
  if (row.averageBreach && row.average !== null) out.push(`entry average ${fmtAvg(row.average)}`);
  if (row.cappingBreach && row.cappingAverage != null) out.push(`capping average ${fmtAvg(row.cappingAverage)}`);
  for (const b of row.breachDays.slice(0, maxDays)) out.push(`${b.value} on ${dayLabel(b.date)}`);
  const more = row.breachDays.length - maxDays;
  if (more > 0) out.push(`+${more} more day${more === 1 ? "" : "s"}`);
  return out;
}
