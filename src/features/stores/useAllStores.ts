import { useQuery } from "@tanstack/react-query";
import { listAllStores } from "@/services/stores";

/** Every store, in one request. */
export function useAllStores(enabled = true) {
  return useQuery({
    queryKey: ["stores", "all"],
    queryFn: listAllStores,
    enabled,
    staleTime: 60_000,
  });
}
