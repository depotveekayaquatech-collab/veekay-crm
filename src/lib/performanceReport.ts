/**
 * The plain-text performance report people paste into the office group:
 *
 *   Employee name - Harshita
 *   Entries - 460 / 500         (marked / total needed to reach 100%)
 *   Percentage - 92%
 *   No. of stores - 20
 *
 * The first number is what the employee has marked, the second is the total they needed to mark so far this month for 100%; the percentage is marked / total.
 * "Marked" is store-days of THEIR stores that have an entry today, whoever entered it (not only what they typed); it is recounted on every look.
 */
export interface ReportRow {
  employee_id: string;
  employee_name: string;
  stores: number;
  expected: number;
  done: number;
  percent: number;
  /** Everything this person entered on the platform this month, in any store. */
  entries_made?: number;
  /** No store of their own: there is no percentage, only how many entries they made. */
  no_stores?: boolean;
  /** Entries whose number this person changed this month (a Team Lead's job). */
  corrected?: number;
  is_team_lead?: boolean;
}

/** Who the report is for: everyone, a performance band, or one employee ("emp:<id>"). */
export type Who = "all" | "under50" | "under85" | `emp:${string}`;

export function pickEmployees<T extends ReportRow>(rows: T[], who: Who): T[] {
  if (who === "all") return rows;
  if (who === "under50") return rows.filter((r) => !r.no_stores && r.percent < 50);
  if (who === "under85") return rows.filter((r) => !r.no_stores && r.percent < 85);
  const id = who.slice(4);
  return rows.filter((r) => r.employee_id === id);
}

const n = (v: number) => v.toLocaleString("en-IN");

/** One employee's four lines. */
export function formatEmployee(r: ReportRow): string {
  const fixed = r.is_team_lead || (r.corrected ?? 0) > 0 ? [`Entries corrected - ${n(r.corrected ?? 0)}`] : [];
  if (r.no_stores) return [`Employee name - ${r.employee_name}`, `Entries made - ${n(r.entries_made ?? 0)}`, ...fixed, "No. of stores - 0"].join("\n");
  return [`Employee name - ${r.employee_name}`, `Entries - ${n(r.done)} / ${n(r.expected)}`, `Percentage - ${r.percent}%`, ...fixed, `No. of stores - ${n(r.stores)}`].join("\n");
}

/**
 * One line saying what the figures cover, so the pasted text can still be read on its own days later: how many days were counted and when it was taken. Every
 * day from the 1st to yesterday is counted, holidays included: holidays belong to attendance and never change an entry count. The figures are recounted on
 * every look, so entries added late to earlier days raise them.
 */
export function basisLine(days: number, takenAt?: string): string {
  const taken = takenAt ? new Date(takenAt).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "";
  return `Counted over ${days} day${days === 1 ? "" : "s"}, holidays included${taken ? `. Taken ${taken} IST` : ""}`;
}

/** The whole message: a heading line saying what it is, what it counted (`basis`, see basisLine), then one block per employee with a blank line between. Empty when there is nobody to report. */
export function formatReport(heading: string, rows: ReportRow[], basis?: string): string {
  if (!rows.length) return "";
  return [heading, "Entries = marked / total needed for 100%", ...(basis ? [basis] : []), "", rows.map(formatEmployee).join("\n\n")].join("\n");
}
