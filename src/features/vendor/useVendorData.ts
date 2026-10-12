import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { vendorApi } from "@/features/vendor/vendorApi";

const FRESH = 30_000;

export const useStores = () => useQuery({ queryKey: ["vendor", "stores"], queryFn: vendorApi.stores, staleTime: 5 * 60_000 });

export const useOrders = (p: Parameters<typeof vendorApi.orders>[0]) =>
  useQuery({ queryKey: ["vendor", "orders", p], queryFn: () => vendorApi.orders(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useDailyOrders = (p: Parameters<typeof vendorApi.dailyOrders>[0]) =>
  useQuery({ queryKey: ["vendor", "daily", p], queryFn: () => vendorApi.dailyOrders(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useTickets = (p: Parameters<typeof vendorApi.tickets>[0]) =>
  useQuery({ queryKey: ["vendor", "tickets", p], queryFn: () => vendorApi.tickets(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useTicket = (id: string) => useQuery({ queryKey: ["vendor", "ticket", id], queryFn: () => vendorApi.ticket(id), staleTime: FRESH });

export const useDocuments = (p: Parameters<typeof vendorApi.documents>[0]) =>
  useQuery({ queryKey: ["vendor", "documents", p], queryFn: () => vendorApi.documents(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useBottles = (p: Parameters<typeof vendorApi.bottles>[0]) =>
  useQuery({ queryKey: ["vendor", "bottles", p], queryFn: () => vendorApi.bottles(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useDeliveries = (p: Parameters<typeof vendorApi.deliveries>[0]) =>
  useQuery({ queryKey: ["vendor", "deliveries", p], queryFn: () => vendorApi.deliveries(p), placeholderData: keepPreviousData, staleTime: FRESH });

/** Polled once a minute: this is what puts the unread badge on the Alerts tab. */
export const useNotifications = (p: { page?: number } = {}) =>
  useQuery({ queryKey: ["vendor", "notifications", p], queryFn: () => vendorApi.notifications(p), refetchInterval: 60_000, staleTime: 15_000 });

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (ids?: string[]) => vendorApi.markRead(ids), onSuccess: () => qc.invalidateQueries({ queryKey: ["vendor", "notifications"] }) });
}

/** After any write, the lists it can change are refetched. */
export function useVendorMutation<V, R>(fn: (v: V) => Promise<R>, invalidate: string[]) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: ["vendor", k] }))),
  });
}
