import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { closeStore, createStore, deleteAllStores, movePlatform, importStoresFile, listStores, syncStartDates, syncStores, updateStore } from "@/services/stores";
import { listPartners } from "@/services/partners";
import { pushToast } from "@/lib/toast";
import type { StoreInput } from "@/types/store";

interface Filters {
  regionId?: string;
  partner?: string;
  state?: string;
  storeStatus?: string;
  search?: string;
}

export function useStores(page: number, filters: Filters) {
  return useQuery({
    queryKey: ["stores", page, filters],
    queryFn: () => listStores({ page, pageSize: 20, ...filters }),
  });
}

export function usePartners(enabled = true) {
  return useQuery({ queryKey: ["partners"], queryFn: listPartners, staleTime: 5 * 60_000, enabled });
}

export function useStoreMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["stores"] });
    qc.invalidateQueries({ queryKey: ["duplicate-stores"] });
    qc.invalidateQueries({ queryKey: ["store-import-issues"] });
    qc.invalidateQueries({ queryKey: ["regions"] });
    qc.invalidateQueries({ queryKey: ["store-vendors"] });
  };

  const create = useMutation({
    mutationFn: (input: StoreInput) => createStore(input),
    onSuccess: () => {
      invalidate();
      pushToast("Store added.", "success");
    },
  });

  const update = useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<StoreInput> }) => updateStore(id, input),
    onSuccess: () => {
      invalidate();
      pushToast("Store updated.", "success");
    },
  });

  const close = useMutation({
    mutationFn: (id: string) => closeStore(id),
    onSuccess: () => {
      invalidate();
      pushToast("Store closed.", "success");
    },
  });

  const sync = useMutation({
    mutationFn: (platform?: string) => syncStores(platform),
    onSuccess: (results) => {
      invalidate();
      const created = results.reduce((s, r) => s + r.created, 0);
      const updated = results.reduce((s, r) => s + r.updated, 0);
      pushToast(`Sheet sync done — ${created} added, ${updated} updated.`, "success");
    },
    onError: (err) => {
      pushToast(err instanceof Error ? err.message : "Sync failed.", "error");
    },
  });

  const importFile = useMutation({
    mutationFn: ({ platform, file, allowMismatch }: { platform: string; file: File; allowMismatch?: boolean }) =>
      importStoresFile(platform, file, allowMismatch),
    onSuccess: (r) => {
      // refetch every store list + dashboard numbers so the new stores show up immediately
      invalidate();
      qc.invalidateQueries({ queryKey: ["order-insights"] });
      qc.invalidateQueries({ queryKey: ["pending"] });
      pushToast(
        r.withoutStartDate ? `Import done — ${r.created} added, ${r.updated} updated. ${r.withoutStartDate} new stores need a start date.` : `Import done — ${r.created} added, ${r.updated} updated.`,
        "success",
      );
    },
  });

  const removeAll = useMutation({
    mutationFn: ({ platform, confirm }: { platform: string; confirm: string }) => deleteAllStores(platform, confirm),
    onSuccess: (r) => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["order-insights"] });
      qc.invalidateQueries({ queryKey: ["pending"] });
      pushToast(`${r.storesDeleted} ${r.platform} stores removed.`, "success");
    },
  });

  const move = useMutation({
    mutationFn: ({ from, to, contains, dryRun }: { from: string; to: string; contains: string; dryRun: boolean }) =>
      movePlatform(from, to, contains, dryRun),
    onSuccess: (r) => {
      if (r.dryRun) return;
      invalidate();
      qc.invalidateQueries({ queryKey: ["order-insights"] });
      qc.invalidateQueries({ queryKey: ["pending"] });
      pushToast(`${r.moved} stores moved from ${r.from} to ${r.to}.`, "success");
    },
  });

  const startDates = useMutation({
    mutationFn: ({ platform, replaceExisting, dryRun, vendor }: { platform: string; replaceExisting: boolean; dryRun: boolean; vendor?: string }) =>
      syncStartDates(platform, replaceExisting, dryRun, vendor),
    onSuccess: (r) => {
      if (r.dryRun) return;
      invalidate();
      for (const k of ["inventory", "pending", "order-insights", "matrix"]) qc.invalidateQueries({ queryKey: [k] });
      pushToast(`Start dates updated on ${r.toChange} store${r.toChange === 1 ? "" : "s"}.`, "success");
    },
  });

  return { create, update, close, sync, importFile, removeAll, move, startDates };
}
