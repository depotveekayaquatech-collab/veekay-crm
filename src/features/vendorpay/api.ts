import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";

/** Money arrives as a 2-decimal string ("123456.00"), never a float. */
export type Money = string;

export interface VendorChoice {
  vendorCode: string;
  name: string;
  city: string | null;
}

export interface MonthFigures {
  month: string;
  opening: Money;
  monthTotal: Money;
  paid: Money;
  pending: Money;
  closing: Money;
}

export interface SummaryRow {
  vendorCode: string;
  name: string;
  city: string | null;
  monthTotal: Money;
  paid: Money;
  pending: Money;
  closing: Money;
}

export interface SummaryTotals {
  vendors: number;
  monthTotal: Money;
  paid: Money;
  pending: Money;
  closing: Money;
}

export interface SummaryPage {
  month: string;
  items: SummaryRow[];
  total: number;
  page: number;
  pageSize: number;
  totals: SummaryTotals;
}

export interface LedgerEntry {
  entryDate: string;
  entryType: "BILL" | "PAYMENT";
  voucherNo: string;
  narration: string | null;
  amount: Money;
}

export interface VendorDetail {
  vendor: VendorChoice;
  month: MonthFigures;
  /** Oldest first, ending with the selected month. */
  history: MonthFigures[];
  entries: LedgerEntry[];
  entriesTruncated: boolean;
}

export interface Freshness {
  lastUpdated: string | null;
  lastSource: string | null;
  ageMinutes: number | null;
  stale: boolean;
  staleHours: number;
  neverSynced: boolean;
}

/** The server's sort names for the "All vendors" table. */
export type SortKey = "name" | "city" | "code" | "month_total" | "paid" | "pending" | "closing";
export type SortDirection = "asc" | "desc";

export const PAGE_SIZE = 25;
export const HISTORY_MONTHS = 12;
const VENDOR_LIST_LIMIT = 1000;
const FRESHNESS_REFRESH_MS = 5 * 60_000;

export function useFreshness() {
  return useQuery({
    queryKey: ["vendorpay", "status"],
    queryFn: async () => camelize<Freshness>(await apiRequest("/vendor-payments/status")),
    refetchInterval: FRESHNESS_REFRESH_MS,
  });
}

export function useVendorChoices() {
  return useQuery({
    queryKey: ["vendorpay", "vendors"],
    queryFn: async () => camelize<VendorChoice[]>(await apiRequest(`/vendor-payments/vendors?limit=${VENDOR_LIST_LIMIT}`)),
    staleTime: 5 * 60_000,
  });
}

export function useSummary(month: string, sort: SortKey, direction: SortDirection, page: number) {
  return useQuery({
    queryKey: ["vendorpay", "summary", month, sort, direction, page],
    queryFn: async () => {
      const p = new URLSearchParams({ month, sort, direction, page: String(page), page_size: String(PAGE_SIZE) });
      return camelize<SummaryPage>(await apiRequest(`/vendor-payments/summary?${p}`));
    },
    placeholderData: keepPreviousData,
  });
}

export function useVendorDetail(vendorCode: string, month: string) {
  return useQuery({
    queryKey: ["vendorpay", "vendor", vendorCode, month],
    enabled: Boolean(vendorCode),
    queryFn: async () => {
      const p = new URLSearchParams({ month, months: String(HISTORY_MONTHS) });
      return camelize<VendorDetail>(await apiRequest(`/vendor-payments/vendors/${encodeURIComponent(vendorCode)}?${p}`));
    },
    placeholderData: keepPreviousData,
  });
}
