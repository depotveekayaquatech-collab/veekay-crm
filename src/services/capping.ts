import { camelize } from "@/lib/camel";
import { apiRequest } from "@/services/api";

/** One live Zepto store with its latest capping (bottles per day). */
export interface CapRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  /** The capping in force today, or on the last day of the chosen month; null when the store has none. */
  capping: number | null;
  /** The capping the store started the chosen month with, so a change inside the month shows. */
  startCapping: number | null;
}

export interface CapList {
  today: string;
  month: string;
  monthLabel: string;
  /** False for a finished month, which can be read but not changed. */
  isCurrent: boolean;
  total: number;
  withoutCapping: number;
  rows: CapRow[];
}

export interface CapHistoryRow {
  id: string;
  /** Null = the capping was removed on that date. */
  capping: number | null;
  effectiveFrom: string;
  changedBy: string | null;
  changedByCode: string | null;
  createdAt: string;
}

export interface CapHistory {
  storeId: string;
  outletId: string;
  outletName: string;
  today: string;
  /** Newest first. */
  rows: CapHistoryRow[];
}

export interface CapChangeResult {
  id: string;
  storeId: string;
  capping: number | null;
  effectiveFrom: string;
  /** The capping in force today, after this change. */
  currentCapping: number | null;
}

export type CapTone = "ok" | "warn" | "over" | "none";

/** The two collective averages (all live stores together) the "Reduce capping" alert is based on. */
export interface CapOverall {
  /** All bottles / all store-days that have an entry, two decimals; null when there are none. */
  entryAverage: number | null;
  entryDays: number;
  total: number;
  /** All capping / all store-days with a capping in force since the store's entries started, two decimals; null when none. */
  cappingAverage: number | null;
  cappingDays: number;
  entryBreach: boolean;
  cappingBreach: boolean;
  alert: boolean;
  reasons: ("average" | "capping")[];
  status: CapTone;
}

export interface CapAlert {
  from: string;
  to: string;
  today: string;
  limit: number;
  amberMargin: number;
  overall: CapOverall;
}

/** Every live Zepto store with its latest capping; with a month, the capping it had at the end of that month. */
export async function getCappingList(month?: string): Promise<CapList> {
  return camelize<CapList>(await apiRequest(`/capping${month ? `?month=${encodeURIComponent(month)}` : ""}`));
}

export async function getCappingHistory(storeId: string): Promise<CapHistory> {
  return camelize<CapHistory>(await apiRequest(`/capping/history?storeId=${encodeURIComponent(storeId)}`));
}

/** The "Reduce capping" alert for a period (this month so far by default). */
export async function getCappingAlert(from?: string, to?: string): Promise<CapAlert> {
  const q = new URLSearchParams();
  if (from) q.set("from", from);
  if (to) q.set("to", to);
  return camelize<CapAlert>(await apiRequest(`/capping/alert${q.toString() ? `?${q}` : ""}`));
}

/** Administrator / manager: set a store's capping. It applies from today (a store's first capping from the day its entries started). */
export async function changeCapping(storeId: string, capping: number): Promise<CapChangeResult> {
  return camelize<CapChangeResult>(await apiRequest("/capping/change", { method: "POST", body: { storeId, capping } }));
}

/** Administrator / manager: remove a store's capping. The history keeps what it was. */
export async function removeCapping(storeId: string): Promise<CapChangeResult> {
  return camelize<CapChangeResult>(await apiRequest("/capping/remove", { method: "POST", body: { storeId } }));
}

// ---------------------------------------------------------------- monthly usage against the limit (the dashboard / analysis view)

/** OK below the warning line, NEAR from 80% of the monthly limit, AHEAD faster than the daily capping allows so far this month, OVER above the limit. */
export type CapLevel = "OVER" | "AHEAD" | "NEAR" | "OK" | "NO_CAP";

export interface UsageRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  /** The store's vendor; null when none is set. */
  vendorName: string | null;
  ownerCode: string | null;
  ownerName: string | null;
  /** Bottles per day: the capping in force today. */
  dailyCap: number | null;
  /** The most the store may take in a month: dailyCap x the days in that month. */
  monthlyCap: number | null;
  /** Bottles marked so far this month, every entry whoever entered it. */
  used: number;
  entries: number;
  highestDay: number;
  lastEntry: string | null;
  remaining: number | null;
  excess: number;
  percent: number | null;
  /** The capping pro-rated to today; null for a finished month or a store with no capping. */
  allowedToDate: number | null;
  aheadBy: number | null;
  alert: CapLevel;
}

export interface CapUsage {
  month: string;
  monthLabel: string;
  months: string[];
  warnPercent: number;
  summary: { over: number; ahead: number; near: number; ok: number; noCap: number; total: number; entries: number; bottles: number };
  rows: UsageRow[];
}

/** This month's over-limit / ahead-of-pace stores for the signed-in person (needs capping.alerts, or the platform's own login). */
export interface CapAlerts {
  month: string;
  monthLabel: string;
  day: number;
  daysInMonth: number;
  over: number;
  ahead: number;
  rows: UsageRow[];
}

export async function getCappingUsage(month?: string): Promise<CapUsage> {
  return camelize<CapUsage>(await apiRequest(`/capping/usage${month ? `?month=${encodeURIComponent(month)}` : ""}`));
}

export async function getCappingAlerts(): Promise<CapAlerts> {
  return camelize<CapAlerts>(await apiRequest("/capping/alerts"));
}

// ---------------------------------------------------------------- overflow: who is over, who has room (read-only)

/** One day on which a store's bottles were above the capping in force that day. */
export interface OverDay {
  date: string;
  bottles: number;
  cap: number;
  overBy: number;
}

export interface OverflowRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  vendorName: string | null;
  dailyCap: number | null;
  monthlyCap: number | null;
  used: number;
  /** Bottles above the monthly limit (dailyCap x the days in that month). */
  excess: number;
  /** What is left of the monthly limit; 0 for a store with no capping or one that is over. */
  room: number;
  percent: number | null;
  daysOver: number;
  /** The bottles above the day's capping, added up over the days it was exceeded. */
  dailyExcess: number;
  overDays: OverDay[];
}

export interface CapOverflow {
  month: string;
  monthLabel: string;
  months: string[];
  summary: {
    stores: number;
    storesOverMonth: number;
    monthExcess: number;
    storesOverDays: number;
    daysOver: number;
    dailyExcess: number;
    storesWithRoom: number;
    room: number;
    used: number;
    limit: number;
    overTotal: number;
  };
  rows: OverflowRow[];
}

export async function getCappingOverflow(month?: string): Promise<CapOverflow> {
  return camelize<CapOverflow>(await apiRequest(`/capping/overflow${month ? `?month=${encodeURIComponent(month)}` : ""}`));
}
