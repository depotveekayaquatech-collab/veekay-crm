import { useQuery } from "@tanstack/react-query";
import { listStores } from "@/services/stores";

/** Every store, unpaged — for the assignment picker. */
export function useAllStores(enabled = true) {
  return useQuery({
    queryKey: ["stores", "all"],
    queryFn: () => listStores({ page: 1, pageSize: 100 }),
    enabled,
    select: (p) => p.items,
  });
}
