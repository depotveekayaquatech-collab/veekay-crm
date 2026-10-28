/** Every date on the capping page is an Asia/Kolkata day, whatever the browser's own time zone is. */
const IST = "Asia/Kolkata";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Today as YYYY-MM-DD in India. */
export function istToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** "2026-10-01" -> "01-Oct". */
export function dayLabel(iso: string): string {
  return `${iso.slice(8, 10)}-${MONTHS[Number(iso.slice(5, 7)) - 1]}`;
}

/** "2026-10-01" -> "01-Oct-2026". */
export function dateLabel(iso: string): string {
  return `${dayLabel(iso)}-${iso.slice(0, 4)}`;
}

/** An average with exactly two decimals ("9.40"); a dash when there is none. */
export function fmtAvg(v: number | null | undefined): string {
  return v == null ? "—" : v.toFixed(2);
}
