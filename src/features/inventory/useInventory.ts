import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { toInventory } from "@/types/inventory";

export function useInventory(partner: string) {
  return useQuery({
    queryKey: ["inventory", partner],
    queryFn: async () => toInventory(await apiRequest(`/orders/inventory${partner ? `?partner=${partner}` : ""}`)),
    staleTime: 30_000,
  });
}
