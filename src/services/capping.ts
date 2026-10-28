import { camelize } from "@/lib/camel";
import { apiRequest } from "@/services/api";

/** One live Zepto store with its latest capping (bottles per day) and the day its actual entries started. */
export interface CapRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  /** The capping in force today; null when the store has none. */
  capping: number | null;
  /** The store's start date, else its first day with bottles; null when it has never been supplied. */
  startDate: string | null;
}

export interface CapList {
  today: string;
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

/** Every live Zepto store with its latest capping. */
export async function getCappingList(): Promise<CapList> {
  return camelize<CapList>(await apiRequest("/capping"));
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
