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

/** The last 12 months, this one first, as YYYY-MM (the same months the backend offers). */
export function recentMonths(today: string = istToday()): string[] {
  let y = Number(today.slice(0, 4));
  let m = Number(today.slice(5, 7));
  const out: string[] = [];
  for (let i = 0; i < 12; i++) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m -= 1;
    if (m === 0) { y -= 1; m = 12; }
  }
  return out;
}

/** "2026-10" -> "October 2026". */
export function monthName(month: string): string {
  return new Date(`${month}-01T12:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

/** The dates the alert is asked for: the whole month, or only up to today for the month in progress. */
export function monthRange(month: string, today: string = istToday()): { from: string; to: string } {
  const [y, m] = month.split("-").map(Number);
  const last = `${month}-${String(new Date(Date.UTC(y, m, 0)).getUTCDate()).padStart(2, "0")}`;
  return { from: `${month}-01`, to: last > today ? today : last };
}
