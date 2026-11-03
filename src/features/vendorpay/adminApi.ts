import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";
import type { Money } from "@/features/vendorpay/api";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface SyncLog {
  id: string;
  startedAt: string;
  finishedAt: string | null;
  source: "API" | "CSV";
  mode: string | null;
  periodFrom: string | null;
  periodTo: string | null;
  triggeredBy: string | null;
  rowsReceived: number;
  rowsInserted: number;
  rowsUpdated: number;
  rowsUnchanged: number;
  rowsDeleted: number;
  rowsUnmatched: number;
  rowsRejected: number;
  status: "SUCCESS" | "PARTIAL" | "FAILED";
  errorMessage: string | null;
}

export interface AdminVendor {
  id: string;
  vendorCode: string;
  name: string;
  city: string | null;
  openingBalance: Money;
  openingDate: string | null;
  isActive: boolean;
}

export interface VendorForm {
  vendorCode: string;
  name: string;
  city: string;
  openingBalance: string;
  openingDate: string;
}

export const EMPTY_VENDOR: VendorForm = { vendorCode: "", name: "", city: "", openingBalance: "", openingDate: "" };

export interface CodeCheck {
  vendorCode: string;
  valid: boolean;
  exists: boolean;
  aliasOf: string | null;
  message: string | null;
}

export interface UnmatchedGroup {
  vendorCode: string | null;
  accountName: string;
  rows: number;
  bills: Money;
  payments: Money;
  firstDate: string;
  lastDate: string;
  suggestedName: string;
}

export interface KeyInfo {
  configured: boolean;
  endpointPath: string;
  header: string;
  envVariable: string;
  staleHours: number;
  vendorCodeRegex: string;
  instructions: string;
}

export interface RowError {
  row: number;
  message: string;
  voucherNo: string;
}

export interface SyncResult {
  status: "SUCCESS" | "PARTIAL" | "FAILED";
  dryRun: boolean;
  received: number;
  inserted: number;
  updated: number;
  unchanged: number;
  deleted: number;
  unmatched: number;
  rejected: number;
  errors: RowError[];
  errorsTruncated: boolean;
  unmatchedCodes: string[];
  sample: { row: number; vendorCode: string | null; date: string; type: string; amount: string; voucherNo: string }[];
}

export interface CsvPreview {
  headers: string[];
  mapping: Record<string, string | null>;
  missingFields: string[];
  totalRows: number;
  result: SyncResult | null;
}

export const ADMIN_PAGE_SIZE = 20;
/** Everything the vendor-payments screens show depends on the ledger, so any admin write refreshes all of it. */
const ALL = ["vendorpay"];

const body = (v: VendorForm) => ({
  vendor_code: v.vendorCode,
  name: v.name,
  city: v.city.trim() || null,
  opening_balance: v.openingBalance.trim() || "0",
  opening_date: v.openingDate || null,
});

export function useSyncLogs(page: number) {
  return useQuery({
    queryKey: ["vendorpay", "admin", "logs", page],
    queryFn: async () => camelize<Page<SyncLog>>(await apiRequest(`/vendor-payments/admin/sync-logs?page=${page}&page_size=${ADMIN_PAGE_SIZE}`)),
    placeholderData: keepPreviousData,
  });
}

export function useAdminVendors(q: string, page: number) {
  return useQuery({
    queryKey: ["vendorpay", "admin", "vendors", q, page],
    queryFn: async () => {
      const p = new URLSearchParams({ q, page: String(page), page_size: String(ADMIN_PAGE_SIZE) });
      return camelize<Page<AdminVendor>>(await apiRequest(`/vendor-payments/admin/vendors?${p}`));
    },
    placeholderData: keepPreviousData,
  });
}

export const checkCode = async (code: string) =>
  camelize<CodeCheck>(await apiRequest(`/vendor-payments/admin/vendors/check-code?code=${encodeURIComponent(code)}`, { silent: true }));

export function useVendorMutations() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ALL });
  const create = useMutation({
    mutationFn: (v: VendorForm) => apiRequest("/vendor-payments/admin/vendors", { method: "POST", body: body(v) }),
    onSuccess: () => {
      pushToast("Vendor added.", "success");
      return done();
    },
  });
  const update = useMutation({
    mutationFn: ({ code, patch }: { code: string; patch: Record<string, unknown> }) =>
      apiRequest(`/vendor-payments/admin/vendors/${encodeURIComponent(code)}`, { method: "PATCH", body: patch }),
    onSuccess: () => {
      pushToast("Vendor saved.", "success");
      return done();
    },
  });
  return { create, update };
}

/** The editable fields only: vendor_code is never sent for an existing vendor. */
export const formToPatch = (v: VendorForm) => ({ name: v.name, city: v.city.trim() || null, opening_balance: v.openingBalance.trim() || "0", opening_date: v.openingDate || null });

export function useUnmatched() {
  return useQuery({
    queryKey: ["vendorpay", "admin", "unmatched"],
    queryFn: async () => camelize<UnmatchedGroup[]>(await apiRequest("/vendor-payments/admin/unmatched")),
  });
}

export function useResolveMutations() {
  const qc = useQueryClient();
  const done = (r: { moved: number; vendorCode: string }) => {
    pushToast(`${r.moved} entries moved to ${r.vendorCode}.`, "success");
    return qc.invalidateQueries({ queryKey: ALL });
  };
  const selector = (g: UnmatchedGroup) => ({ vendor_code: g.vendorCode, account_name: g.vendorCode ? null : g.accountName });
  const createVendor = useMutation({
    mutationFn: async ({ group, vendor }: { group: UnmatchedGroup; vendor: VendorForm }) =>
      camelize<{ moved: number; vendorCode: string }>(await apiRequest("/vendor-payments/admin/unmatched/create-vendor", { method: "POST", body: { ...selector(group), new_vendor: body(vendor) } })),
    onSuccess: done,
  });
  const mapToVendor = useMutation({
    mutationFn: async ({ group, target }: { group: UnmatchedGroup; target: string }) =>
      camelize<{ moved: number; vendorCode: string }>(await apiRequest("/vendor-payments/admin/unmatched/map", { method: "POST", body: { ...selector(group), map_to_vendor_code: target } })),
    onSuccess: done,
  });
  return { createVendor, mapToVendor };
}

export function useKeyInfo() {
  return useQuery({
    queryKey: ["vendorpay", "admin", "key"],
    queryFn: async () => camelize<KeyInfo>(await apiRequest("/vendor-payments/admin/key-info")),
  });
}

export const generateKey = async () => camelize<{ key: string; note: string }>(await apiRequest("/vendor-payments/admin/key-info/generate", { method: "POST" }));

function csvForm(file: File, mapping: Record<string, string | null> | null): FormData {
  const form = new FormData();
  form.append("file", file);
  if (mapping) form.append("mapping", JSON.stringify(Object.fromEntries(Object.entries(mapping).filter(([, v]) => v))));
  return form;
}

/** The mapping's keys are our field names (account_name ...) and are sent back as they are, so they must not be camel-cased. */
export async function previewCsv(file: File, mapping: Record<string, string | null> | null): Promise<CsvPreview> {
  const raw = await apiRequest<{ mapping: Record<string, string | null> }>("/vendor-payments/admin/csv/preview", { method: "POST", body: csvForm(file, mapping) });
  return { ...camelize<CsvPreview>(raw), mapping: raw.mapping };
}

export function useImportCsv() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, mapping }: { file: File; mapping: Record<string, string | null> }) =>
      camelize<SyncResult>(await apiRequest("/vendor-payments/admin/csv/import", { method: "POST", body: csvForm(file, mapping) })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ALL }),
  });
}

export async function downloadCsvTemplate(): Promise<void> {
  const blob = await apiBlob("/vendor-payments/admin/csv/template");
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "vendor-payments-template.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
