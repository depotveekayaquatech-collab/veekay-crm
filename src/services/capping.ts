import { camelize } from "@/lib/camel";
import { apiRequest } from "@/services/api";

export type CapLevel = "OVER" | "NEAR" | "OK" | "NO_CAP";

export interface CapRow {
  storeId: string;
  outletId: string;
  outletName: string;
  state: string | null;
  city: string | null;
  ownerCode: string | null;
  ownerName: string | null;
  monthlyCap: number | null;
  used: number;
  entries: number;
  remaining: number | null;
  excess: number;
  percent: number | null;
  alert: CapLevel;
}

export interface CapReport {
  success: boolean;
  month: string;
  monthLabel: string;
  months: string[];
  warnPercent: number;
  summary: { over: number; near: number; ok: number; noCap: number; total: number };
  rows: CapRow[];
}

export interface CapImportResult {
  rowsRead: number;
  added: number;
  updated: number;
  kept: number;
  unknownStores: number;
  invalid: number;
  warnings: string[];
}

export async function getCappingReport(month?: string): Promise<CapReport> {
  const q = month ? `?month=${encodeURIComponent(month)}` : "";
  return camelize<CapReport>(await apiRequest(`/capping${q}`));
}

/** Set a store's monthly cap; null removes it. */
export async function setStoreCap(storeId: string, monthlyCap: number | null): Promise<void> {
  await apiRequest(`/capping/stores/${storeId}`, { method: "PUT", body: { monthly_cap: monthlyCap } });
}

/** Developer: load caps from the configured Google sheet. Existing CRM caps are kept unless `overwrite`. */
export async function syncCapsFromSheet(overwrite: boolean): Promise<CapImportResult> {
  return camelize<CapImportResult>(await apiRequest(`/capping/sync?overwrite=${overwrite}`, { method: "POST" }));
}

export async function importCapsFile(file: File, overwrite: boolean): Promise<CapImportResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("overwrite", String(overwrite));
  return camelize<CapImportResult>(await apiRequest("/capping/import", { method: "POST", body: form }));
}
