import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createRegion, deactivateRegion, listRegions, updateRegion } from "@/services/regions";
import { pushToast } from "@/lib/toast";
import type { RegionInput } from "@/types/region";

export function useRegions(page: number) {
  return useQuery({
    queryKey: ["regions", page],
    queryFn: () => listRegions({ page, pageSize: 20 }),
  });
}

/** All regions, unpaged — for populating <Select> dropdowns elsewhere. */
export function useAllRegions() {
  return useQuery({
    queryKey: ["regions", "all"],
    queryFn: () => listRegions({ page: 1, pageSize: 100 }),
    select: (p) => p.items,
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
