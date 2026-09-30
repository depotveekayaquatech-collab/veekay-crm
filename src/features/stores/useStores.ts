import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { closeStore, createStore, importStoresFile, listStores, syncStores, updateStore } from "@/services/stores";
import { listPartners } from "@/services/partners";
import { pushToast } from "@/lib/toast";
import type { StoreInput } from "@/types/store";

interface Filters {
  regionId?: string;
  partner?: string;
  state?: string;
  storeStatus?: string;
}

export function useStores(page: number, filters: Filters) {
  return useQuery({
    queryKey: ["stores", page, filters],
    queryFn: () => listStores({ page, pageSize: 20, ...filters }),
  });
}

export function usePartners() {
  return useQuery({ queryKey: ["partners"], queryFn: listPartners, staleTime: 5 * 60_000 });
}

export function useStoreMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["stores"] });
    qc.invalidateQueries({ queryKey: ["regions"] });
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
    mutationFn: ({ platform, file }: { platform: string; file: File }) => importStoresFile(platform, file),
    onSuccess: (r) => {
      // refetch every store list + dashboard numbers so the new stores show up immediately
      invalidate();
      qc.invalidateQueries({ queryKey: ["order-insights"] });
      qc.invalidateQueries({ queryKey: ["pending"] });
      pushToast(`Import done — ${r.created} added, ${r.updated} updated.`, "success");
    },
  });

  return { create, update, close, sync, importFile };
}
