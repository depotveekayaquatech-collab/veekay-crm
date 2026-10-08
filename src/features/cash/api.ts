import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";

export type PurchaseKind = "OFFICE" | "STORE";

export interface Reason {
  code: string;
  label: string;
}

export interface StoreChoice {
  id: string;
  name: string;
  code: string;
  platform: string | null;
  state: string | null;
}

export interface CashOptions {
  officeReasons: Reason[];
  storeReasons: Reason[];
  stores: StoreChoice[];
  /** True for admins / accounts, who see everyone's purchases. */
  canViewAll: boolean;
  maxAmount: string;
}

export interface CashPurchase {
  id: string;
  kind: PurchaseKind;
  purchaseDate: string;
  storeId: string | null;
  storeName: string | null;
  storeCode: string | null;
  category: string;
  categoryLabel: string;
  otherReason: string | null;
  amount: string;
  notes: string | null;
  hasProof: boolean;
  proofName: string | null;
  addedBy: string | null;
  createdAt: string;
}

export interface CashList {
  items: CashPurchase[];
  total: number;
  page: number;
  pageSize: number;
  amountTotal: string;
  officeTotal: string;
  storeTotal: string;
}

export interface CashFilters {
  kind: "" | PurchaseKind;
  start: string;
  end: string;
  category: string;
  q: string;
}

export interface CashInput {
  kind: PurchaseKind;
  storeId: string | null;
  purchaseDate: string;
  category: string;
  otherReason: string;
  amount: string;
  notes: string;
  /** Photo or PDF of the payment proof (required). */
  proof: File;
}

export const PAGE_SIZE = 20;

function query(f: CashFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.kind) p.set("kind", f.kind);
  if (f.start) p.set("start", f.start);
  if (f.end) p.set("end", f.end);
  if (f.category) p.set("category", f.category);
  if (f.q.trim()) p.set("q", f.q.trim());
  return p;
}

export function useCashOptions() {
  return useQuery({
    queryKey: ["cash-options"],
    queryFn: async () => camelize<CashOptions>(await apiRequest("/cash-purchases/options")),
    staleTime: 5 * 60_000,
  });
}

export function useCashPurchases(filters: CashFilters, page: number) {
  return useQuery({
    queryKey: ["cash-purchases", filters, page],
    queryFn: async () => {
      const p = query(filters);
      p.set("page", String(page));
      p.set("page_size", String(PAGE_SIZE));
      return camelize<CashList>(await apiRequest(`/cash-purchases?${p}`));
    },
    placeholderData: keepPreviousData,
  });
}

export function useAddCashPurchase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (i: CashInput) => {
      const form = new FormData();
      form.set("kind", i.kind);
      if (i.kind === "STORE" && i.storeId) form.set("store_id", i.storeId);
      form.set("purchase_date", i.purchaseDate);
      form.set("category", i.category);
      if (i.category === "OTHER") form.set("other_reason", i.otherReason.trim());
      form.set("amount", i.amount);
      if (i.notes.trim()) form.set("notes", i.notes.trim());
      form.set("proof", i.proof);
      return camelize<CashPurchase>(await apiRequest("/cash-purchases", { method: "POST", body: form }));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cash-purchases"] });
      pushToast("Purchase recorded.", "success");
    },
  });
}

/** Opens the stored payment proof in a new tab. */
export async function openProof(id: string): Promise<void> {
  // Open the tab first (inside the click) so the browser doesn't block it as a popup after the download.
  const tab = window.open("", "_blank");
  try {
    const blob = await apiBlob(`/cash-purchases/${id}/proof`);
    const url = URL.createObjectURL(blob);
    if (tab) tab.location.href = url;
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    tab?.close();
    throw e;
  }
}

export async function downloadCashSheet(filters: CashFilters): Promise<void> {
  const blob = await apiBlob(`/cash-purchases/export?${query(filters)}`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const scope = filters.kind === "OFFICE" ? "office" : filters.kind === "STORE" ? "stores" : "all";
  a.href = url;
  a.download = `cash-purchases-${scope}-${filters.start || "start"}_${filters.end || "today"}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export const inr = (v: string | number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(v));
