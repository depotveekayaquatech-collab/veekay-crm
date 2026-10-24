import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/api/client";
import { staffApi, type CashFilter, type LeaveType } from "@/api/staff";
import type { EntryChange, EntryStatus } from "@/lib/format";

const FRESH = 30_000;

export const useAttendanceToday = () =>
  useQuery({ queryKey: ["s-attendance"], queryFn: staffApi.attendanceToday, staleTime: 15_000, refetchInterval: 60_000 });

export const useMyEntries = (days: number) => useQuery({ queryKey: ["s-my-entries", days], queryFn: () => staffApi.myEntries(days), staleTime: 15_000 });

export const usePayslips = () => useQuery({ queryKey: ["s-payslips"], queryFn: staffApi.payslips, staleTime: FRESH });

/** Salaries paid to this employee whose "salary received" popup has not been shown yet. */
export const useUnseenPayslips = (enabled = true) =>
  useQuery({ queryKey: ["s-payslips-unseen"], queryFn: staffApi.unseenPayslips, staleTime: 15_000, refetchInterval: 60_000, enabled, retry: false });

export const useLeaves = () => useQuery({ queryKey: ["s-leaves"], queryFn: staffApi.leaves, staleTime: FRESH });

export const useMyStores = (enabled = true) => useQuery({ queryKey: ["s-stores"], queryFn: staffApi.myStores, staleTime: FRESH, enabled });

export interface CalendarDay { day: number; date: string; marked: boolean; count: number | null; source: string | null; entered_by?: string | null; entered_at?: string | null; is_today: boolean; is_future: boolean;
  /** You entered this day. */
  mine?: boolean;
  /** A colleague at your own level marked it: shown as marked, with no number, name or time. */
  masked?: boolean;
  /** Someone more senior (Team Lead, administrator, the developer) entered it: you can see it, you cannot change it. */
  by_higher?: boolean;
  /** Where the entry stands (Submitted / Verified by Team Lead / Reviewed by Reviewer). */
  verification?: EntryStatus | null;
  /** The latest change somebody made to the number after it was entered: who, in which role, when, old and new. */
  changed?: EntryChange | null }
export interface Calendar {
  store_id: string; store_name: string; store_code: string; year: number; month: number; month_label: string; days: CalendarDay[];
  /** False when this month cannot be marked by the caller (view only). */
  can_mark?: boolean;
  /** For last month: the last day it can still be marked. */
  open_until?: string | null;
}

/** A store's calendar: this month, or the given year and month (last month, while it is open for entries). */
export const useCalendar = (storeId: string, ym?: { year: number; month: number }) =>
  useQuery({
    queryKey: ["s-calendar", storeId, ym?.year ?? 0, ym?.month ?? 0],
    queryFn: () => request<Calendar>(`/orders/calendar?store_id=${storeId}${ym ? `&year=${ym.year}&month=${ym.month}` : ""}`),
    staleTime: 10_000,
  });

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

/** `status` is present only when the SERVER confirms the entry is stored ("saved", or "already_saved" for a retry of the same number). */
export interface MarkResult {
  saved: number; failed: number;
  results: { order_date: string; ok: boolean; error: string | null; status?: "saved" | "already_saved" | null; entry_id?: string | null; saved_at?: string | null; version?: number | null }[];
}

export function useMarkMany() {
  const qc = useQueryClient();
  return useMutation({
    // `key` stays the same while the person retries the same submission, so a lost answer never makes a second entry or a false "already marked".
    mutationFn: (b: { store_id: string; entries: { order_date: string; bottle_count: number }[]; key?: string }) =>
      request<MarkResult>("/orders/mark-many", { method: "POST", body: { store_id: b.store_id, entries: b.entries }, idempotencyKey: b.key, clientTime: true }),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ["s-calendar"] }), qc.invalidateQueries({ queryKey: ["s-stores"] })]),
  });
}

/** An employee changes (or clears, with no count) an entry they marked themselves. */
export function useCorrectEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { store_id: string; order_date: string; bottle_count: number | null }) =>
      request<unknown>("/orders/my-entry", { method: "PATCH", body: b }),
    onSuccess: () => Promise.all(["s-calendar", "s-stores", "s-my-entries"].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

export function useStaffWrite<V, R>(fn: (v: V) => Promise<R>, invalidate: string[]) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: [k] }))) });
}

export type { LeaveType };
