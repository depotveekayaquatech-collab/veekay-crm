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

/** A change dated before today asks for a confirmation first. */
export function isBackdated(effectiveFrom: string, today: string = istToday()): boolean {
  return effectiveFrom < today;
}
