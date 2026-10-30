import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createRegion, deactivateRegion, listRegions, updateRegion } from "@/services/regions";
import { pushToast } from "@/lib/toast";
import type { RegionInput } from "@/types/region";
import { selectableRegions } from "@/lib/selectableRegions";

export function useRegions(page: number) {
  return useQuery({
    queryKey: ["regions", page],
    queryFn: () => listRegions({ page, pageSize: 20 }),
  });
}

/**
 * Regions for the <Select> dropdowns elsewhere (unpaged). A region that was deactivated AND has no stores is never offered: nothing can belong to it, so it
 * only adds a choice that does not exist (an empty region the store import created from a sheet name, for example). One that still has stores stays, and so
 * does any region in `keep` (the one the record being edited already uses), so editing never loses a saved value. The Regions page itself lists everything.
 */
export function useAllRegions(keep: readonly (string | null | undefined)[] = []) {
  return useQuery({
    queryKey: ["regions", "all"],
    queryFn: () => listRegions({ page: 1, pageSize: 100 }),
    select: (p) => selectableRegions(p.items, keep),
  });
}

export function useRegionMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["regions"] });

  const create = useMutation({
    mutationFn: (input: RegionInput) => createRegion(input),
    onSuccess: () => {
      invalidate();
      pushToast("Region created.", "success");
    },
  });

  const update = useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<RegionInput> & { is_active?: boolean } }) =>
      updateRegion(id, input),
    onSuccess: () => {
      invalidate();
      pushToast("Region updated.", "success");
    },
  });

  const deactivate = useMutation({
    mutationFn: (id: string) => deactivateRegion(id),
    onSuccess: () => {
      invalidate();
      pushToast("Region deactivated.", "success");
    },
  });

  return { create, update, deactivate };
}
