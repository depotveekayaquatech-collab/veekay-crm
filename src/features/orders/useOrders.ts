import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  correctEntry,
  correctOwnEntry,
  getCalendar,
  getDailyOverview,
  getInsights,
  getMyStores,
  importOrdersFile,
  markManyOrders,
  markOrder,
  syncOrders,
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
      for (const key of ["daily-overview", "my-stores", "pending", "capping"]) qc.invalidateQueries({ queryKey: [key] });
      pushToast("Order marked.", "success");
    },
  });
}

export function useMarkManyOrders() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      storeId,
      entries,
    }: {
      storeId: string;
      entries: { orderDate: string; bottleCount: number }[];
    }) => markManyOrders(storeId, entries),
    onSuccess: (data, vars) => {
      qc.invalidateQueries({ queryKey: ["calendar", vars.storeId] });
      for (const key of ["daily-overview", "my-stores", "pending", "order-insights", "capping"]) {
        qc.invalidateQueries({ queryKey: [key] });
      }
      if (data.failed === 0) {
        pushToast(`${data.saved} order${data.saved === 1 ? "" : "s"} marked successfully.`, "success");
      } else if (data.saved > 0) {
        pushToast(`${data.saved} saved, ${data.failed} skipped.`, "info");
      } else {
        pushToast(`Failed to mark entries: ${data.results[0]?.error ?? "validation error"}`, "error");
      }
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
      for (const key of ["daily-overview", "my-stores", "pending", "capping"]) qc.invalidateQueries({ queryKey: [key] });
      pushToast(vars.count === null ? "Entry cleared." : "Entry corrected.", "success");
    },
  });
}

export function useCorrectOwnEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ storeId, date, count }: { storeId: string; date: string; count: number | null }) =>
      correctOwnEntry(storeId, date, count),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["calendar", vars.storeId] });
      for (const key of ["daily-overview", "my-stores", "pending", "capping"]) qc.invalidateQueries({ queryKey: [key] });
      pushToast(vars.count === null ? "Entry removed." : "Entry corrected.", "success");
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
      for (const key of ["calendar", "daily-overview", "order-insights", "report", "pending", "my-stores", "capping"]) {
        qc.invalidateQueries({ queryKey: [key] });
      }
      pushToast(`Order sheet imported — ${r.created} added, ${r.updated} updated.`, "success");
    },
  });
}

export function useSyncOrders() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ platform, overwrite }: { platform?: string; overwrite?: boolean } = {}) => syncOrders(platform, overwrite),
    onSuccess: (results) => {
      for (const key of ["calendar", "daily-overview", "order-insights", "report", "pending", "my-stores", "capping"]) {
        qc.invalidateQueries({ queryKey: [key] });
      }
      const added = results.reduce((n, r) => n + r.created, 0);
      const changed = results.reduce((n, r) => n + r.updated, 0);
      pushToast(`Order sheet synced — ${added} added, ${changed} updated.`, "success");
    },
  });
}
