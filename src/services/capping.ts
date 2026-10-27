import { camelize } from "@/lib/camel";
import { apiBlob, apiRequest } from "@/services/api";

/** AHEAD: more bottles than the cap pro-rated to today (current month only), still under the cap. */
export type CapLevel = "OVER" | "AHEAD" | "NEAR" | "OK" | "NO_CAP";

export interface CapRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  ownerCode: string | null;
  ownerName: string | null;
  /** Bottles per day, as in the capping sheet. */
  dailyCap: number | null;
  /** The most the store may take in a month: dailyCap x 30. */
  monthlyCap: number | null;
  used: number;
  entries: number;
  remaining: number | null;
  excess: number;
  percent: number | null;
  /** Cap pro-rated to today; null for a finished month or a store with no cap. */
  allowedToDate: number | null;
  aheadBy: number | null;
  alert: CapLevel;
}

export interface CapReport {
  success: boolean;
  month: string;
  monthLabel: string;
  months: string[];
  warnPercent: number;
  summary: { over: number; ahead: number; near: number; ok: number; noCap: number; total: number };
  rows: CapRow[];
}

/** This month's over-cap / ahead-of-pace stores for the signed-in employee (needs capping.alerts). */
export interface CapAlerts {
  month: string;
  monthLabel: string;
  day: number;
  daysInMonth: number;
  over: number;
  ahead: number;
  rows: CapRow[];
}

export interface CapImportResult {
  rowsRead: number;
  added: number;
  updated: number;
  kept: number;
  unknownStores: number;
  /** Names that match more than one store (skipped). */
  ambiguous: number;
  invalid: number;
  /** How the sheet was read, e.g. "stores matched by Outlet Name; columns found from their headings". */
  readAs?: string | null;
  warnings: string[];
}

export async function getCappingReport(month?: string): Promise<CapReport> {
  const q = month ? `?month=${encodeURIComponent(month)}` : "";
  return camelize<CapReport>(await apiRequest(`/capping${q}`));
}

export async function getCappingAlerts(): Promise<CapAlerts> {
  return camelize<CapAlerts>(await apiRequest("/capping/alerts"));
}

/** Set a store's DAILY cap (its monthly limit is that x 30); null removes it. */
export async function setStoreCap(storeId: string, dailyCap: number | null): Promise<void> {
  await apiRequest(`/capping/stores/${storeId}`, { method: "PUT", body: { daily_cap: dailyCap } });
}

/** Developer: load caps from the configured Google sheet. Existing CRM caps are kept unless `overwrite`. */
export async function syncCapsFromSheet(overwrite: boolean): Promise<CapImportResult> {
  return camelize<CapImportResult>(await apiRequest(`/capping/sync?overwrite=${overwrite}`, { method: "POST" }));
}

/** Developer or administrator: load caps from an uploaded .csv / .xlsx (Outlet ID + the daily capping number). */
export async function importCapsFile(file: File, overwrite: boolean): Promise<CapImportResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("overwrite", String(overwrite));
  return camelize<CapImportResult>(await apiRequest("/capping/import", { method: "POST", body: form }));
}

// ---------------------------------------------------------------- capping history, the capping sheet and the average-vs-limit summary

export type CapTone = "ok" | "warn" | "over" | "none";

export interface BreachDay {
  date: string;
  value: number;
}

/** One store over the chosen period: its average daily entry against the limit, and why it is (or is not) in alert. */
export interface CapSummaryRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  /** Average of the days that have an entry (a zero counts), two decimals; null when there are none. */
  average: number | null;
  /** Average capping over the days of the period (up to today) that had one in force, two decimals; null when none. */
  cappingAverage: number | null;
  cappingDays: number;
  /** Days in the period marked as 0 capping (absent from an older API). */
  cappingZeroDays?: number;
  entryDays: number;
  total: number;
  maxDay: number | null;
  /** The capping in force today. */
  currentCapping: number | null;
  breachDays: BreachDay[];
  alert: boolean;
  /** Which conditions put the store in alert: the entry average, the capping average, a single day. */
  reasons: ("average" | "capping" | "day")[];
  averageBreach: boolean;
  cappingBreach: boolean;
  dayBreach: boolean;
  /** Card colour: over = in alert (red), warn = within the margin of the limit (amber), ok = green, none = no entries. */
  status: CapTone;
}

/** The collective figures the alert is based on: all stores together, not store by store. */
export interface CapOverall {
  /** All bottles / all days that have an entry, two decimals; null when there are none. */
  entryAverage: number | null;
  entryDays: number;
  total: number;
  /** All capping / all store-days with a capping in force (up to today), two decimals; null when none. */
  cappingAverage: number | null;
  cappingDays: number;
  entryBreach: boolean;
  cappingBreach: boolean;
  alert: boolean;
  reasons: ("average" | "capping")[];
  status: CapTone;
}

export interface CapSummary {
  from: string;
  to: string;
  today: string;
  limit: number;
  amberMargin: number;
  totals: { stores: number; inAlert: number };
  /** Absent when the web app is newer than the API (during a deploy): the page then simply shows no collective figures. */
  overall?: CapOverall;
  rows: CapSummaryRow[];
}

export interface CapHistoryRow {
  id: string;
  capping: number;
  effectiveFrom: string;
  changedBy: string | null;
  changedByCode: string | null;
  createdAt: string;
}

export interface CapZeroDay {
  id: string;
  day: string;
  changedBy: string | null;
  changedByCode: string | null;
  createdAt: string;
}

export interface CapHistory {
  storeId: string;
  outletId: string;
  outletName: string;
  today: string;
  rows: CapHistoryRow[];
  /** Days marked as 0 capping, newest first (absent from an older API). */
  zeroDays?: CapZeroDay[];
}

export interface CapSheetRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  /** The capping in force on each date of `dates`; null before the store's first change. */
  cells: (number | null)[];
}

export interface CapSheet {
  from: string;
  to: string;
  dates: string[];
  rows: CapSheetRow[];
}

export interface CapChangeResult {
  id: string;
  storeId: string;
  capping: number;
  effectiveFrom: string;
  /** True when the date is in the past. */
  backdated: boolean;
  /** The capping in force today, after this change. */
  currentCapping: number | null;
}

export type SheetFormat = "csv" | "xlsx";

function sheetQuery(from: string, to: string, storeId?: string): string {
  const q = new URLSearchParams({ from, to });
  if (storeId) q.set("storeId", storeId);
  return q.toString();
}

export async function getCappingSummary(from: string, to: string): Promise<CapSummary> {
  return camelize<CapSummary>(await apiRequest(`/capping/summary?${sheetQuery(from, to)}`));
}

export async function getCappingHistory(storeId: string): Promise<CapHistory> {
  return camelize<CapHistory>(await apiRequest(`/capping/history?storeId=${encodeURIComponent(storeId)}`));
}

export async function getCappingSheet(from: string, to: string, storeId?: string): Promise<CapSheet> {
  return camelize<CapSheet>(await apiRequest(`/capping/sheet?${sheetQuery(from, to, storeId)}`));
}

/** Administrator / manager: a store's capping from a date (today or earlier). */
export async function changeCapping(storeId: string, capping: number, effectiveFrom: string): Promise<CapChangeResult> {
  return camelize<CapChangeResult>(await apiRequest("/capping/change", { method: "POST", body: { storeId, capping, effectiveFrom } }));
}

/** Administrator / manager: the store's capping is 0 on these days (the days either side keep theirs). */
export async function markZeroDays(storeId: string, days: string[]): Promise<{ marked: string[]; already: string[] }> {
  return camelize(await apiRequest("/capping/zero-days", { method: "POST", body: { storeId, days } }));
}

/** Take a day marked by mistake back to its normal capping. */
export async function unmarkZeroDay(storeId: string, day: string): Promise<void> {
  await apiRequest(`/capping/zero-days?storeId=${encodeURIComponent(storeId)}&day=${encodeURIComponent(day)}`, { method: "DELETE" });
}

/** Saves the capping sheet as a file. */
export async function downloadCappingSheet(from: string, to: string, storeId: string | undefined, format: SheetFormat): Promise<void> {
  const blob = await apiBlob(`/capping/sheet/download?${sheetQuery(from, to, storeId)}&format=${format}`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `zepto-capping-sheet_${from}_to_${to}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
