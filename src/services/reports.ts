import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { toPending, toReport, type PendingEntries, type ReportGroup, type SalesReport } from "@/types/report";

/** Optional narrowing for the report: platform slug, region name, state. */
export interface ReportFilters {
  partner?: string;
  region?: string;
  state?: string;
  /** Keep only the top N breakdown rows — totals, `rowCount` and the daily series stay complete. */
  limit?: number;
}

export async function getReport(start: string, end: string, groupBy: ReportGroup, filters: ReportFilters = {}): Promise<SalesReport> {
  const qs = new URLSearchParams({ start, end, group_by: groupBy });
  if (filters.partner) qs.set("partner", filters.partner);
  if (filters.region) qs.set("region", filters.region);
  if (filters.state) qs.set("state", filters.state);
  if (filters.limit) qs.set("limit", String(filters.limit));
  return toReport(await apiRequest(`/orders/report?${qs}`));
}

export async function getPending(dayOffset: number, partner: string): Promise<PendingEntries> {
  const qs = new URLSearchParams({ day_offset: String(dayOffset) });
  if (partner) qs.set("partner", partner);
  return toPending(await apiRequest(`/orders/pending?${qs}`));
}

export function useReport(start: string, end: string, groupBy: ReportGroup, filters: ReportFilters = {}) {
  return useQuery({
    queryKey: ["report", start, end, groupBy, filters.partner ?? "", filters.region ?? "", filters.state ?? "", filters.limit ?? 0],
    queryFn: () => getReport(start, end, groupBy, filters),
    placeholderData: (prev) => prev,
    enabled: Boolean(start && end && start <= end),
  });
}

export function usePending(dayOffset: number, partner: string) {
  return useQuery({
    queryKey: ["pending", dayOffset, partner],
    queryFn: () => getPending(dayOffset, partner),
  });
}
