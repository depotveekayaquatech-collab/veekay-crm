import { describe, expect, it } from "vitest";
import { buildLines, lineProblems, lineTotal, type DailyMatched, type DailyParsed, type DailyUnmatched } from "./dailySheet";
import { SKIP } from "./sheetPicker";

const day = (d: number, count: number) => ({ date: `2026-10-${String(d).padStart(2, "0")}`, count });

const matched = (over: Partial<DailyMatched> = {}): DailyMatched => ({
  row: 2, sheet_name: "Saket", store_id: "s1", store_name: "Blinkit Saket", code: "BLK-1", platform: "blinkit",
  total: 15, sheet_total: 15, entries: [day(1, 5), day(2, 5), day(3, 5)], issues: [], ...over,
});
const unmatched = (over: Partial<DailyUnmatched> = {}): DailyUnmatched => ({
  row: 3, name: "Saket new", total: 4, reason: "No store with that name or Outlet ID.", suggestions: [],
  sheet_total: 4, entries: [day(2, 1), day(4, 3)], issues: [], ...over,
});
const parsed = (m: DailyMatched[], u: DailyUnmatched[] = []): DailyParsed => ({ file: "a.csv", month: "2026-10", rows: m.length + u.length, matched: m, unmatched: u, warnings: [] });
const noInfo = () => undefined;

describe("lineProblems", () => {
  it("passes when the days add up to the sheet's total", () => {
    const [line] = buildLines(parsed([matched()]), {}, noInfo);
    expect(lineTotal(line)).toBe(15);
    expect(lineProblems(line)).toEqual([]);
  });

  it("flags a total that does not match the days, and says both numbers", () => {
    const [line] = buildLines(parsed([matched({ sheet_total: 20 })]), {}, noInfo);
    expect(lineProblems(line)).toEqual(["The days add up to 15, but the sheet's total count is 20."]);
  });

  it("does not check a store whose sheet gave no total", () => {
    const [line] = buildLines(parsed([matched({ sheet_total: null })]), {}, noInfo);
    expect(lineProblems(line)).toEqual([]);
  });

  it("reports cell problems from the sheet and a store with no days", () => {
    const [bad] = buildLines(parsed([matched({ issues: ["Day 2: 'abc' is not a whole number of zero or more."] })]), {}, noInfo);
    expect(lineProblems(bad)).toHaveLength(1);
    const [empty] = buildLines(parsed([matched({ entries: [], sheet_total: null })]), {}, noInfo);
    expect(lineProblems(empty)).toEqual(["No daily numbers."]);
  });
});

describe("buildLines", () => {
  it("leaves out unmatched rows nobody has pointed at a store, and rows marked skip", () => {
    const p = parsed([matched()], [unmatched({ row: 3 }), unmatched({ row: 4 })]);
    expect(buildLines(p, {}, noInfo)).toHaveLength(1);
    expect(buildLines(p, { 3: SKIP }, noInfo)).toHaveLength(1);
  });

  it("gives a chosen unmatched row its own days, named from the store list or, failing that, the suggestion", () => {
    const sug = { store_id: "s2", name: "Blinkit Gurugram", code: "BLK-4901" };
    const p = parsed([matched()], [unmatched({ suggestions: [sug] })]);
    const fromList = buildLines(p, { 3: "s2" }, (id) => (id === "s2" ? { name: "From the list", code: "L-1" } : undefined));
    expect(fromList.map((l) => l.name)).toEqual(["Blinkit Saket", "From the list"]);
    const fromSuggestion = buildLines(p, { 3: "s2" }, noInfo);
    expect(fromSuggestion[1]).toMatchObject({ name: "Blinkit Gurugram", code: "BLK-4901", sheetTotal: 4 });
    expect(lineTotal(fromSuggestion[1])).toBe(4);
  });

  it("adds an unmatched row to the store it is pointed at when that store already has a row", () => {
    const p = parsed([matched({ entries: [day(1, 5), day(2, 5)], sheet_total: 10 })], [unmatched()]);
    const [line] = buildLines(p, { 3: "s1" }, noInfo);
    expect(line.entries).toEqual([day(1, 5), day(2, 6), day(4, 3)]);
    expect(line.sheetTotal).toBe(14);
    expect(lineProblems(line)).toEqual([]);
  });

  it("drops the check when one of the merged rows stated no total", () => {
    const p = parsed([matched({ sheet_total: 15 })], [unmatched({ sheet_total: null })]);
    const [line] = buildLines(p, { 3: "s1" }, noInfo);
    expect(line.sheetTotal).toBeNull();
  });
});
