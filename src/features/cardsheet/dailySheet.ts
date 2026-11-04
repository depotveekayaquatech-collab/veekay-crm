import type { DayCount } from "./randomCounts";
import { SKIP, type PickerRow } from "./sheetPicker";

/** What POST /developer/card-sheet/daily-preview returns for a sheet of store, total count and one column per day. */
export interface DailyMatched {
  row: number;
  sheet_name: string;
  store_id: string;
  store_name: string;
  code: string;
  platform: string | null;
  total: number;
  sheet_total: number | null;
  entries: DayCount[];
  issues: string[];
}

export interface DailyUnmatched extends PickerRow {
  sheet_total: number | null;
  entries: DayCount[];
  issues: string[];
}

export interface DailyParsed {
  file: string;
  month: string;
  rows: number;
  matched: DailyMatched[];
  unmatched: DailyUnmatched[];
  warnings: string[];
}

/** One card's worth of the sheet: a store, the entries written for it, and the total the sheet states (null = none given). */
export interface DailyLine {
  storeId: string;
  name: string;
  code: string;
  entries: DayCount[];
  sheetTotal: number | null;
  issues: string[];
}

export const lineTotal = (line: DailyLine): number => line.entries.reduce((s, e) => s + e.count, 0);

function merge(a: DailyLine, b: DailyLine): DailyLine {
  const byDate = new Map<string, number>();
  for (const e of [...a.entries, ...b.entries]) byDate.set(e.date, (byDate.get(e.date) ?? 0) + e.count);
  return {
    ...a,
    entries: [...byDate].sort(([x], [y]) => x.localeCompare(y)).map(([date, count]) => ({ date, count })),
    sheetTotal: a.sheetTotal === null || b.sheetTotal === null ? null : a.sheetTotal + b.sheetTotal,
    issues: [...a.issues, ...b.issues],
  };
}

/** Everything that could get a card: the matched stores plus the unmatched rows the person pointed at a store (two rows for one store are added together). */
export function buildLines(
  parsed: DailyParsed,
  choice: Record<number, string>,
  storeInfo: (id: string) => { name: string; code: string } | undefined,
): DailyLine[] {
  const out = new Map<string, DailyLine>();
  const add = (line: DailyLine) => {
    const prev = out.get(line.storeId);
    out.set(line.storeId, prev ? merge(prev, line) : line);
  };
  for (const m of parsed.matched) {
    add({ storeId: m.store_id, name: m.store_name, code: m.code, entries: m.entries, sheetTotal: m.sheet_total, issues: m.issues });
  }
  for (const u of parsed.unmatched) {
    const id = choice[u.row];
    if (!id || id === SKIP) continue;
    const suggested = u.suggestions.find((s) => s.store_id === id);
    const known = storeInfo(id) ?? (suggested && { name: suggested.name, code: suggested.code });
    add({ storeId: id, name: known?.name ?? u.name, code: known?.code ?? "", entries: u.entries, sheetTotal: u.sheet_total, issues: u.issues });
  }
  return [...out.values()];
}

/** Why this store can't be printed yet (empty = it can). A sheet that states no total is not checked against one. */
export function lineProblems(line: DailyLine): string[] {
  const total = lineTotal(line);
  const out = [...line.issues];
  if (line.entries.length === 0) out.push("No daily numbers.");
  if (line.sheetTotal !== null && line.sheetTotal !== total) out.push(`The days add up to ${total}, but the sheet's total count is ${line.sheetTotal}.`);
  return out;
}
