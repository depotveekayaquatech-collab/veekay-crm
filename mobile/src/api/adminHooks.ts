import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/api/admin";

export const useSyncStatus = () => useQuery({ queryKey: ["a-sync"], queryFn: adminApi.syncStatus, staleTime: 30_000 });
export const useInsights = (enabled: boolean) => useQuery({ queryKey: ["a-insights"], queryFn: adminApi.insights, enabled, staleTime: 30_000 });
export const usePending = (dayOffset: number, enabled = true) =>
  useQuery({ queryKey: ["a-pending", dayOffset], queryFn: () => adminApi.pending(dayOffset), enabled, staleTime: 30_000 });
export const useLeavesAll = (status: string, enabled = true) =>
  useQuery({ queryKey: ["a-leaves", status], queryFn: () => adminApi.leaves(status), enabled, staleTime: 15_000 });
export const useBottleSummary = (enabled: boolean) => useQuery({ queryKey: ["a-bottle-summary"], queryFn: adminApi.bottleSummary, enabled, staleTime: 60_000 });
export const useOverdue = (page: number) =>
  useQuery({ queryKey: ["a-overdue", page], queryFn: () => adminApi.overdueBottles(page), placeholderData: keepPreviousData, staleTime: 60_000 });
export const useDueBills = (enabled = true) => useQuery({ queryKey: ["a-bills"], queryFn: adminApi.dueBills, enabled, staleTime: 60_000 });

export function useReviewLeave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; approve: boolean; note: string }) => adminApi.reviewLeave(v.id, v.approve, v.note),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["a-leaves"] }),
  });
}

/** "Sync now": the server pulls the sheets, then everything the app shows is read again from the CRM. */
export function useSyncNow() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: adminApi.syncRun, onSuccess: () => qc.invalidateQueries() });
}
