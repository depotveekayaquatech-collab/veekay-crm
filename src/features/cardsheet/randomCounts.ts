export interface DayCount {
  date: string; // YYYY-MM-DD
  count: number;
}

export const MAX_DAYS = 366;
export const MAX_TOTAL = 100000;

function parse(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

/** Every date from start to end inclusive, as YYYY-MM-DD (calendar days, no timezone drift). */
export function datesBetween(start: string, end: string): string[] {
  const out: string[] = [];
  const last = parse(end);
  for (let t = parse(start); t <= last && out.length <= MAX_DAYS; t = new Date(t.getTime() + 86_400_000)) {
    out.push(t.toISOString().slice(0, 10));
  }
  return out;
}

/** Shares `total` bottles out at random across the days: whole numbers, never negative, summing exactly to `total`. */
export function randomDistribution(total: number, days: string[], allowZero = true): DayCount[] {
  // Without zero days every day starts with 1 and only the rest is shared out (needs total >= days).
  const base = allowZero ? 0 : 1;
  const counts = new Array<number>(days.length).fill(base);
  for (let i = 0; i < total - base * days.length; i++) counts[Math.floor(Math.random() * days.length)]++;
  return days.map((date, i) => ({ date, count: counts[i] }));
}

/** Like randomDistribution but avoids handing back the same split as `previous` (when another split exists). */
export function freshDistribution(total: number, days: string[], previous?: DayCount[], allowZero = true): DayCount[] {
  const same = (a: DayCount[]) => previous?.length === a.length && previous.every((p, i) => p.count === a[i].count);
  let next = randomDistribution(total, days, allowZero);
  for (let tries = 0; tries < 10 && same(next); tries++) next = randomDistribution(total, days, allowZero);
  return next;
}

export function fmtDay(iso: string): string {
  const d = parse(iso);
  return `${String(d.getUTCDate()).padStart(2, "0")}-${d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" })}-${d.getUTCFullYear()}`;
}
