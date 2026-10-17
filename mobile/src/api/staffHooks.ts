import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/api/client";
import { staffApi, type CashFilter, type LeaveType } from "@/api/staff";

const FRESH = 30_000;

export const useAttendanceToday = () =>
  useQuery({ queryKey: ["s-attendance"], queryFn: staffApi.attendanceToday, staleTime: 15_000, refetchInterval: 60_000 });

export const useLeaves = () => useQuery({ queryKey: ["s-leaves"], queryFn: staffApi.leaves, staleTime: FRESH });

export const useMyStores = (enabled = true) => useQuery({ queryKey: ["s-stores"], queryFn: staffApi.myStores, staleTime: FRESH, enabled });

export interface CalendarDay { day: number; date: string; marked: boolean; count: number | null; source: string | null; is_today: boolean; is_future: boolean }
export interface Calendar { store_id: string; store_name: string; store_code: string; year: number; month: number; month_label: string; days: CalendarDay[] }

export const useCalendar = (storeId: string) =>
  useQuery({ queryKey: ["s-calendar", storeId], queryFn: () => request<Calendar>(`/orders/calendar?store_id=${storeId}`), staleTime: 10_000 });

/** Polled once a minute: puts the unread badge on the bell. */
export const useStaffAlerts = () =>
  useQuery({ queryKey: ["s-alerts"], queryFn: () => staffApi.alerts(), refetchInterval: 60_000, staleTime: 15_000 });

export function useMarkStaffAlertsRead() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (ids?: string[]) => staffApi.markAlertsRead(ids), onSuccess: () => qc.invalidateQueries({ queryKey: ["s-alerts"] }) });
}

export const useScanStores = () => useQuery({ queryKey: ["s-scan-stores"], queryFn: staffApi.scanStores, staleTime: 5 * 60_000 });
export const useCashOptions = () => useQuery({ queryKey: ["s-cash-options"], queryFn: staffApi.cashOptions, staleTime: 5 * 60_000 });
export const useCashList = (page: number, filter: CashFilter = {}) =>
  useQuery({ queryKey: ["s-cash", page, filter], queryFn: () => staffApi.cashList({ page, page_size: 30, ...filter }), placeholderData: keepPreviousData, staleTime: FRESH });

export interface MarkResult { saved: number; failed: number; results: { order_date: string; ok: boolean; error: string | null }[] }

export function useMarkMany() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { store_id: string; entries: { order_date: string; bottle_count: number }[] }) =>
      request<MarkResult>("/orders/mark-many", { method: "POST", body: b }),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ["s-calendar"] }), qc.invalidateQueries({ queryKey: ["s-stores"] })]),
  });
}

export function useStaffWrite<V, R>(fn: (v: V) => Promise<R>, invalidate: string[]) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: [k] }))) });
}

export type { LeaveType };
