import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { toPending, toReport, type PendingEntries, type ReportGroup, type SalesReport } from "@/types/report";

export async function getReport(start: string, end: string, groupBy: ReportGroup): Promise<SalesReport> {
  const qs = new URLSearchParams({ start, end, group_by: groupBy });
  return toReport(await apiRequest(`/orders/report?${qs}`));
}

export async function getPending(dayOffset: number, partner: string): Promise<PendingEntries> {
  const qs = new URLSearchParams({ day_offset: String(dayOffset) });
  if (partner) qs.set("partner", partner);
  return toPending(await apiRequest(`/orders/pending?${qs}`));
}

export function useReport(start: string, end: string, groupBy: ReportGroup) {
  return useQuery({
    queryKey: ["report", start, end, groupBy],
    queryFn: () => getReport(start, end, groupBy),
    enabled: Boolean(start && end && start <= end),
  });
}

export function usePending(dayOffset: number, partner: string) {
  return useQuery({
    queryKey: ["pending", dayOffset, partner],
    queryFn: () => getPending(dayOffset, partner),
  });
}
