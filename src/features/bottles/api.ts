import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";

export type BottleState = "UNUSED" | "AT_STORE" | "RETURNED" | "RETIRED" | "DELETED" | "OVERDUE";
export type Direction = "IN" | "OUT";

export interface Bottle {
  id: string;
  serial: string;
  status: Exclude<BottleState, "OVERDUE">;
  storeId: string | null;
  storeName: string | null;
  lastInAt: string | null;
  lastOutAt: string | null;
  lastScanAt: string | null;
  daysAtStore: number | null;
  overdue: boolean;
  replacesSerial: string | null;
  replacedBySerial: string | null;
  retiredAt: string | null;
  retireReason: string | null;
}

export interface Scan {
  id: string;
  direction: Direction;
  storeId: string | null;
  storeName: string | null;
  scannedAt: string;
  source: string;
  scannedByName: string | null;
  warning: string | null;
}

export interface ScanResult {
  duplicate: boolean;
  warning: string | null;
  bottle: Bottle;
  scan: Scan;
}

export interface Summary {
  totalActive: number;
  unused: number;
  atStore: number;
  returned: number;
  retired: number;
  deleted: number;
  overdue: number;
  lostAfterDays: number;
}

export interface Batch {
  id: string;
  quantity: number;
  note: string | null;
  createdByName: string;
  createdAt: string;
  firstSerial: string | null;
  lastSerial: string | null;
}

export interface ScanStore {
  id: string;
  name: string;
  code: string;
  city: string | null;
}

export const PAGE_SIZE = 50;
export const LABELS_PER_PDF = 2000;

export function useSummary() {
  return useQuery({ queryKey: ["bottle-summary"], queryFn: async () => camelize<Summary>(await apiRequest("/bottles/summary")), refetchInterval: 60_000 });
}

export function useScanStores() {
  return useQuery({
    queryKey: ["bottle-stores"],
    queryFn: async () => camelize<ScanStore[]>(await apiRequest("/bottles/stores")),
    staleTime: 5 * 60_000,
  });
}

export function useBottles(f: { state: BottleState | ""; q: string; storeId: string }, page: number, enabled = true) {
  return useQuery({
    queryKey: ["bottles", f, page],
    enabled,
    queryFn: async () => {
      const p = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (f.state) p.set("state", f.state);
      if (f.q.trim()) p.set("q", f.q.trim());
      if (f.storeId) p.set("store_id", f.storeId);
      return camelize<{ items: Bottle[]; total: number }>(await apiRequest(`/bottles?${p}`));
    },
    placeholderData: keepPreviousData,
  });
}

export function useBottleDetail(serial: string | null) {
  return useQuery({
    queryKey: ["bottle", serial],
    enabled: Boolean(serial),
    queryFn: async () => camelize<{ bottle: Bottle; scans: Scan[] }>(await apiRequest(`/bottles/lookup/${encodeURIComponent(serial!)}`)),
  });
}

function invalidateAll(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["bottles"] });
  qc.invalidateQueries({ queryKey: ["bottle"] });
  qc.invalidateQueries({ queryKey: ["bottle-summary"] });
}

/** Scans one code. Errors are returned to the caller (the scan screen shows them inline, not as a toast). */
export function useScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { serial: string; direction: Direction; storeId: string }) =>
      camelize<ScanResult>(
        await apiRequest("/bottles/scan", {
          method: "POST",
          silent: true,
          body: { serial: v.serial, direction: v.direction, store_id: v.storeId || null, scan_id: crypto.randomUUID() },
        }),
      ),
    onSuccess: () => invalidateAll(qc),
  });
}

export function useGenerate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { quantity: number; note: string }) =>
      camelize<Batch>(await apiRequest("/bottles/batches", { method: "POST", body: { quantity: v.quantity, note: v.note.trim() || null } })),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ["bottle-batches"] });
      invalidateAll(qc);
      pushToast(`${b.quantity.toLocaleString("en-IN")} new codes created.`, "success");
    },
  });
}

export function useBatches(enabled: boolean) {
  return useQuery({ queryKey: ["bottle-batches"], enabled, queryFn: async () => camelize<Batch[]>(await apiRequest("/bottles/batches")) });
}

export function useReplace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { serial: string; reason: string }) =>
      camelize<{ old: Bottle; new: Bottle }>(await apiRequest(`/bottles/${encodeURIComponent(v.serial)}/replace`, { method: "POST", body: { reason: v.reason.trim() || null } })),
    onSuccess: (r) => {
      invalidateAll(qc);
      pushToast(`Replaced. New code: ${r.new.serial}`, "success");
    },
  });
}

export function useRetire() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { serial: string; reason: string }) =>
      camelize<Bottle>(await apiRequest(`/bottles/${encodeURIComponent(v.serial)}/retire`, { method: "POST", body: { reason: v.reason.trim() || null } })),
    onSuccess: () => {
      invalidateAll(qc);
      pushToast("Bottle retired.", "success");
    },
  });
}

/** Saves an authenticated file (PDF / CSV) from the API. */
export async function downloadFile(path: string, filename: string, openInTab = false): Promise<void> {
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  if (openInTab) window.open(url, "_blank");
  else {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export const labelsPath = (batchId: string, start: number) => `/bottles/batches/${batchId}/labels.pdf?start=${start}&count=${LABELS_PER_PDF}`;
export const csvPath = (batchId: string) => `/bottles/batches/${batchId}/serials.csv`;
export const labelPath = (serial: string) => `/bottles/${encodeURIComponent(serial)}/label.pdf`;

export const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";

export interface DeleteResult {
  deleted: number;
  alreadyDeleted: number;
  /** Batch delete leaves codes that are already in circulation (scanned). */
  skippedInUse: string[];
  notFound: string[];
}

function useDeleter<V>(path: (v: V) => string, body: (v: V) => unknown) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: V) => camelize<DeleteResult>(await apiRequest(path(v), { method: "POST", body: body(v) })),
    onSuccess: (r) => {
      invalidateAll(qc);
      qc.invalidateQueries({ queryKey: ["bottle-batches"] });
      pushToast(`${r.deleted.toLocaleString("en-IN")} code(s) deleted. Their history is kept.`, "success");
    },
  });
}

/** Developer only: delete these codes for good. */
export const useDeleteCodes = () =>
  useDeleter<{ serials: string[]; reason: string }>(() => "/bottles/delete", (v) => ({ serials: v.serials, reason: v.reason.trim() || null }));

export const useDeleteBatch = () =>
  useDeleter<{ batchId: string; reason: string }>((v) => `/bottles/batches/${v.batchId}/delete`, (v) => ({ reason: v.reason.trim() || null }));
