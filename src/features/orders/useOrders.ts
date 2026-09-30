import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  correctEntry,
  getCalendar,
  getDailyOverview,
  getInsights,
  getMyStores,
  importOrdersFile,
  markOrder,
} from "@/services/orders";
import { pushToast } from "@/lib/toast";

export function useMyStores() {
  return useQuery({ queryKey: ["my-stores"], queryFn: getMyStores });
}

export function useCalendar(storeId: string | null, year?: number, month?: number) {
  return useQuery({
    queryKey: ["calendar", storeId, year, month],
    queryFn: () => getCalendar(storeId as string, year, month),
    enabled: Boolean(storeId),
  });
}

export function useInsights() {
  return useQuery({ queryKey: ["order-insights"], queryFn: getInsights, staleTime: 60_000 });
}

export function useDailyOverview(partner: string, dayOffset: number) {
  return useQuery({
    queryKey: ["daily-overview", partner, dayOffset],
    queryFn: () => getDailyOverview(partner, dayOffset),
    enabled: Boolean(partner),
  });
}

export function useMarkOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ storeId, date, count }: { storeId: string; date: string; count: number }) =>
      markOrder(storeId, date, count),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["calendar", vars.storeId] });
      qc.invalidateQueries({ queryKey: ["daily-overview"] });
      pushToast("Order marked.", "success");
    },
  });
}

export function useCorrectEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ storeId, date, count }: { storeId: string; date: string; count: number | null }) =>
      correctEntry(storeId, date, count),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["calendar", vars.storeId] });
      qc.invalidateQueries({ queryKey: ["daily-overview"] });
      pushToast(vars.count === null ? "Entry cleared." : "Entry corrected.", "success");
    },
  });
}

export function useImportOrders() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ platform, file, overwrite }: { platform: string; file: File; overwrite: boolean }) =>
      importOrdersFile(platform, file, overwrite),
    onSuccess: (r) => {
      // everything that shows order numbers must refetch
      for (const key of ["calendar", "daily-overview", "order-insights", "report", "pending", "my-stores"]) {
        qc.invalidateQueries({ queryKey: [key] });
      }
      pushToast(`Order sheet imported — ${r.created} added, ${r.updated} updated.`, "success");
    },
  });
}
