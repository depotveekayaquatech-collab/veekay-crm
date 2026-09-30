import { useQuery } from "@tanstack/react-query";
import { listStores } from "@/services/stores";
import type { Store } from "@/types/store";

const PAGE = 100; // backend page-size cap

/** Every store, unpaged — walks all pages so large imports (hundreds of stores) aren't cut off. */
async function fetchEveryStore(): Promise<Store[]> {
  const first = await listStores({ page: 1, pageSize: PAGE });
  const pages = Math.ceil(first.total / PAGE);
  const rest = await Promise.all(
    Array.from({ length: Math.max(0, pages - 1) }, (_, i) => listStores({ page: i + 2, pageSize: PAGE })),
  );
  return [first, ...rest].flatMap((p) => p.items);
}

export function useAllStores(enabled = true) {
  return useQuery({
    queryKey: ["stores", "all"],
    queryFn: fetchEveryStore,
    enabled,
    staleTime: 60_000,
  });
}
