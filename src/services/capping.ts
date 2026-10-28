import { camelize } from "@/lib/camel";
import { apiRequest } from "@/services/api";

/** One live Zepto store with its latest capping (bottles per day) and the date that capping started. */
export interface CapRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  /** The capping in force today; null when the store has none. */
  capping: number | null;
  since: string | null;
}

export interface CapList {
  today: string;
  total: number;
  withoutCapping: number;
  rows: CapRow[];
}

export interface CapHistoryRow {
  id: string;
  capping: number;
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
  capping: number;
  effectiveFrom: string;
  /** True when the date is in the past. */
  backdated: boolean;
  /** The capping in force today, after this change. */
  currentCapping: number | null;
}

/** Every live Zepto store with its latest capping. */
export async function getCappingList(): Promise<CapList> {
  return camelize<CapList>(await apiRequest("/capping"));
}

export async function getCappingHistory(storeId: string): Promise<CapHistory> {
  return camelize<CapHistory>(await apiRequest(`/capping/history?storeId=${encodeURIComponent(storeId)}`));
}

/** Administrator / manager: a store's capping from a date (today or earlier). */
export async function changeCapping(storeId: string, capping: number, effectiveFrom: string): Promise<CapChangeResult> {
  return camelize<CapChangeResult>(await apiRequest("/capping/change", { method: "POST", body: { storeId, capping, effectiveFrom } }));
}

/** Administrator / manager: move one capping change to another start date (the capping itself stays). */
export async function changeCappingDate(historyId: string, effectiveFrom: string): Promise<{ id: string; capping: number; effectiveFrom: string; was: string; currentCapping: number | null }> {
  return camelize(await apiRequest(`/capping/history/${encodeURIComponent(historyId)}`, { method: "PATCH", body: { effectiveFrom } }));
}
