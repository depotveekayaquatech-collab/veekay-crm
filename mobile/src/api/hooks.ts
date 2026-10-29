import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/api";

const FRESH = 30_000;

/** The vendor / POC login's stores. Pass `enabled = false` where the list comes from somewhere else (an employee login). */
export const useStores = (enabled = true) => useQuery({ queryKey: ["stores"], queryFn: api.stores, staleTime: 5 * 60_000, enabled });

export const useDailyOrders = (p: Parameters<typeof api.dailyOrders>[0]) =>
  useQuery({ queryKey: ["daily", p], queryFn: () => api.dailyOrders(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useOrders = (p: Parameters<typeof api.orders>[0], enabled = true) =>
  useQuery({ queryKey: ["orders", p], queryFn: () => api.orders(p), enabled, staleTime: FRESH });

export const useTickets = (p: Parameters<typeof api.tickets>[0]) =>
  useQuery({ queryKey: ["tickets", p], queryFn: () => api.tickets(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useTicket = (id: string) => useQuery({ queryKey: ["ticket", id], queryFn: () => api.ticket(id), staleTime: FRESH });

export const useDocuments = (p: Parameters<typeof api.documents>[0]) =>
  useQuery({ queryKey: ["documents", p], queryFn: () => api.documents(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useBottles = (p: Parameters<typeof api.bottles>[0]) =>
  useQuery({ queryKey: ["bottles", p], queryFn: () => api.bottles(p), placeholderData: keepPreviousData, staleTime: FRESH });

export const useDeliveries = (p: Parameters<typeof api.deliveries>[0]) =>
  useQuery({ queryKey: ["deliveries", p], queryFn: () => api.deliveries(p), placeholderData: keepPreviousData, staleTime: FRESH });

/** Polled once a minute while the app is open: this puts the unread badge on the Alerts tab. */
export const useNotifications = () =>
  useQuery({ queryKey: ["notifications"], queryFn: () => api.notifications({ page_size: 50 }), refetchInterval: 60_000, staleTime: 15_000 });

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (ids?: string[]) => api.markRead(ids), onSuccess: () => { void qc.invalidateQueries({ queryKey: ["notifications"] }); } });
}

/** After any write, the lists it can change are refetched. */
export function useWrite<V, R>(fn: (v: V) => Promise<R>, invalidate: string[]) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => { for (const k of invalidate) void qc.invalidateQueries({ queryKey: [k] }); },
  });
}
