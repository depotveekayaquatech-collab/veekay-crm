import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";

const BASE = "/developer/cash-adjustments";

export interface StoreChoice {
  id: string;
  name: string;
  code: string;
  platform: string | null;
  state: string | null;
}

export interface AdjustInput {
  storeIds: string[];
  purchaseDate: string;
  amount: string;
  pricePerItem: string;
  quantity: number | null;
}

export interface PreviewRow {
  storeId: string;
  outletCode: string;
  outletName: string;
  hasEntry: boolean;
  employeeEntry: number | null;
  previous: number;
  added: number;
  newTotal: number;
  error: string | null;
}

export interface Preview {
  purchaseDate: string;
  amount: string;
  pricePerItem: string;
  autoQty: number;
  finalQty: number;
  overridden: boolean;
  totalStores: number;
  rows: PreviewRow[];
  canApply: boolean;
}

export interface ApplyResult {
  batchId: string;
  autoQty: number;
  finalQty: number;
  applied: PreviewRow[];
  failed: { storeId: string | null; outletCode: string; outletName: string; error: string }[];
}

export interface HistoryItem {
  id: string;
  batchId: string;
  createdAt: string;
  developer: string;
  outletCode: string;
  outletName: string;
  purchaseDate: string;
  amount: string;
  pricePerItem: string;
  autoQty: number;
  finalQty: number;
  previousQty: number;
  finalOrderQty: number;
  syncCode: string | null;
  purchaseCode: string | null;
  source: string;
  action: string;
}

export interface SyncSummary {
  syncId: string;
  syncCode: string;
  syncedAt: string;
  recordsFound: number;
  newRecords: number;
  changedRecords: number;
  alreadyProcessed: number;
  pendingReview: number;
}

export interface SyncRun {
  syncId: string;
  syncCode: string;
  syncedAt: string;
  developer: string;
  recordsFound: number;
  newRecords: number;
  changedRecords: number;
  alreadyProcessed: number;
  applied: number;
}

export interface SourceSnapshot {
  storeName: string | null;
  storeCode: string | null;
  purchaseDate: string;
  amount: string;
}

export type SyncStatus = "PENDING" | "CHANGED" | "APPLIED" | "SKIPPED";

export interface SyncRecord {
  id: string;
  purchaseCode: string;
  status: SyncStatus;
  storeId: string | null;
  outletCode: string | null;
  outletName: string | null;
  purchaseDate: string;
  amount: string;
  pricePerItem: string | null;
  autoQty: number | null;
  finalQty: number | null;
  overridden: boolean;
  reason: string | null;
  addedBy: string | null;
  syncCode: string | null;
  appliedQty: number | null;
  everApplied: boolean;
  previousSource: SourceSnapshot | null;
  currentSource: SourceSnapshot | null;
}

export interface SyncOverview {
  lastSync: SyncSummary | null;
  counts: Record<SyncStatus, number>;
  items: SyncRecord[];
  total: number;
  page: number;
  pageSize: number;
}

export interface SyncPreviewRow {
  storeId: string | null;
  outletCode: string;
  outletName: string;
  purchaseDate: string;
  employeeEntry: number | null;
  previous: number;
  added: number;
  newTotal: number;
  purchases: { recordId: string; purchaseCode: string; finalQty: number | null; error: string | null }[];
  error: string | null;
}

export interface SyncPreview {
  rows: SyncPreviewRow[];
  totalStores: number;
  totalRecords: number;
  totalQty: number;
  canApply: boolean;
}

export interface SyncApplyResult {
  batchId: string;
  appliedRecords: number;
  appliedRows: SyncPreviewRow[];
  failed: { outletCode: string; outletName: string; purchaseDate: string; error: string }[];
}

export interface RecordEdit {
  storeId?: string;
  purchaseDate?: string;
  amount?: string;
  pricePerItem?: string;
  finalQty?: number | null;
}

export const SYNC_PAGE_SIZE = 50;
export const HISTORY_PAGE_SIZE = 20;

/** Whole items a purchase covers, always rounded UP. Done in cents so 100 / 30 can't be thrown off by float noise. */
export function ceilQty(amount: string | number, price: string | number): number | null {
  const a = Math.round(Number(amount) * 100);
  const p = Math.round(Number(price) * 100);
  if (!Number.isFinite(a) || !Number.isFinite(p) || a <= 0 || p <= 0) return null;
  return Math.ceil(a / p);
}

const post = <T,>(path: string, body?: unknown) => apiRequest<unknown>(`${BASE}${path}`, { method: "POST", body }).then((r) => camelize<T>(r));

async function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export const downloadPurchaseSheet = async () => save(await apiBlob(`${BASE}/purchase-sheet`), "cash-purchase-sheet.xlsx");
export const downloadHistorySheet = async () => save(await apiBlob(`${BASE}/history/export`), "cash-purchase-history.xlsx");

export function useStoreChoices(q: string) {
  return useQuery({
    queryKey: ["cash-adj-stores", q],
    queryFn: async () => camelize<StoreChoice[]>(await apiRequest(`${BASE}/stores?limit=500&q=${encodeURIComponent(q)}`)),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useAdjust() {
  const qc = useQueryClient();
  const body = (i: AdjustInput) => ({
    store_ids: i.storeIds, purchase_date: i.purchaseDate, amount: i.amount, price_per_item: i.pricePerItem, quantity: i.quantity,
  });
  return {
    preview: useMutation({ mutationFn: (i: AdjustInput) => post<Preview>("/preview", body(i)) }),
    apply: useMutation({
      mutationFn: (i: AdjustInput) => post<ApplyResult>("/apply", body(i)),
      onSuccess: (r) => {
        for (const k of ["cash-adj-history", "calendar", "daily-overview", "order-insights", "report", "pending"]) qc.invalidateQueries({ queryKey: [k] });
        pushToast(r.failed.length ? `Applied to ${r.applied.length} stores, ${r.failed.length} failed.` : `Applied to ${r.applied.length} store${r.applied.length === 1 ? "" : "s"}.`, r.failed.length ? "error" : "success");
      },
    }),
  };
}

export function useHistory(page: number, q: string) {
  return useQuery({
    queryKey: ["cash-adj-history", page, q],
    queryFn: async () =>
      camelize<{ items: HistoryItem[]; total: number }>(
        await apiRequest(`${BASE}/history?page=${page}&page_size=${HISTORY_PAGE_SIZE}&q=${encodeURIComponent(q)}`),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useSyncRuns() {
  return useQuery({ queryKey: ["cash-sync-runs"], queryFn: async () => camelize<SyncRun[]>(await apiRequest(`${BASE}/sync/runs`)) });
}

export function useSyncRecords(status: SyncStatus | "", page: number) {
  return useQuery({
    queryKey: ["cash-sync-records", status, page],
    queryFn: async () =>
      camelize<SyncOverview>(await apiRequest(`${BASE}/sync/records?page=${page}&page_size=${SYNC_PAGE_SIZE}${status ? `&status=${status}` : ""}`)),
    placeholderData: keepPreviousData,
  });
}

export function useSyncActions() {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cash-sync-records"] });
    qc.invalidateQueries({ queryKey: ["cash-sync-runs"] });
  };
  return {
    sync: useMutation({ mutationFn: () => post<SyncSummary>("/sync"), onSuccess: refresh }),
    edit: useMutation({
      mutationFn: ({ id, ...e }: RecordEdit & { id: string }) =>
        apiRequest<unknown>(`${BASE}/sync/records/${id}`, {
          method: "PATCH",
          body: {
            ...(e.storeId !== undefined && { store_id: e.storeId }),
            ...(e.purchaseDate !== undefined && { purchase_date: e.purchaseDate }),
            ...(e.amount !== undefined && { amount: e.amount }),
            ...(e.pricePerItem !== undefined && { price_per_item: e.pricePerItem }),
            ...(e.finalQty !== undefined && { final_qty: e.finalQty }),
          },
        }).then((r) => camelize<SyncRecord>(r)),
      onSuccess: refresh,
    }),
    resolve: useMutation({
      mutationFn: ({ id, action }: { id: string; action: "accept_source" | "keep_mine" | "acknowledge" | "reopen" | "skip" | "unskip" }) =>
        post<SyncRecord>(`/sync/records/${id}/resolve`, { action }),
      onSuccess: refresh,
    }),
    standardRate: useMutation({
      mutationFn: ({ price, overwrite }: { price: string; overwrite: boolean }) =>
        post<{ updated: number; kept: number }>("/sync/standard-rate", { price_per_item: price, overwrite }),
      onSuccess: (r) => {
        refresh();
        pushToast(`Standard rate set on ${r.updated} purchase${r.updated === 1 ? "" : "s"}${r.kept ? ` (${r.kept} already had a price and were kept)` : ""}.`, "success");
      },
    }),
    preview: useMutation({ mutationFn: (ids: string[]) => post<SyncPreview>("/sync/preview", { record_ids: ids }) }),
    apply: useMutation({
      mutationFn: (ids: string[]) => post<SyncApplyResult>("/sync/apply", { record_ids: ids }),
      onSuccess: (r) => {
        refresh();
        for (const k of ["cash-adj-history", "calendar", "daily-overview", "order-insights", "report", "pending"]) qc.invalidateQueries({ queryKey: [k] });
        pushToast(r.failed.length ? `Applied ${r.appliedRecords} purchases, ${r.failed.length} store/day failed.` : `Applied ${r.appliedRecords} purchase${r.appliedRecords === 1 ? "" : "s"} to the order sheet.`, r.failed.length ? "error" : "success");
      },
    }),
  };
}

export interface AnalysisStore {
  storeId: string;
  outletCode: string;
  outletName: string;
  platform: string | null;
  state: string | null;
  purchases: number;
  amount: string;
  topReason: string | null;
}

export interface AnalysisVendor {
  rank: number;
  flag: "HIGH" | "WATCH" | "";
  vendor: string;
  vendorNumber: string | null;
  storesWithPurchases: number;
  totalStores: number;
  purchases: number;
  amount: string;
  averageAmount: string;
  lastDate: string;
  reasons: Record<string, number>;
  stores: AnalysisStore[];
}

export interface Analysis {
  totalPurchases: number;
  totalAmount: string;
  vendorsCount: number;
  averagePurchases: number;
  high: number;
  watch: number;
  vendors: AnalysisVendor[];
}

const range = (start: string, end: string) => {
  const p = new URLSearchParams();
  if (start) p.set("start", start);
  if (end) p.set("end", end);
  return p.toString();
};

export function useAnalysis(start: string, end: string) {
  return useQuery({
    queryKey: ["cash-analysis", start, end],
    queryFn: async () => camelize<Analysis>(await apiRequest(`${BASE}/analysis?${range(start, end)}`)),
    placeholderData: keepPreviousData,
  });
}

export const downloadAnalysisSheet = async (start: string, end: string) =>
  save(await apiBlob(`${BASE}/analysis/export?${range(start, end)}`), "cash-purchase-vendor-analysis.xlsx");

export const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
