import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBlob, apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";

/* Zero Review speaks snake_case straight from the server, like the entry audit does. */

export type Mode = "break" | "ignore" | "count";
export type ReviewState = "pending" | "reviewed" | "verified" | "flagged";
export type Severity = "none" | "low" | "medium" | "high" | "critical";

export interface Person { id: string; name: string; code: string }
export interface Reason { value: string; label: string }

export interface ZeroFilterValues {
  from: string;
  to: string;
  regions: string[];
  employees: string[];
  platform: string;
  q: string;
  status: "" | ReviewState;
  n: number;                // consecutive zeros, 0 = off
  unmarked: Mode;
  unmarkedGe: number;
  sort: string;
}

export interface Options {
  regions: { id: string; name: string }[];
  employees: Person[];
  platforms: { slug: string; name: string }[];
  reasons: Reason[];
  grace_days: number;
  weekly_threshold: number;
  default_week: string;
  previous_month: string;
  today: string;
  can_review: boolean;
  can_reopen: boolean;
  level: string;
}

export interface Streak { length: number; start: string; end: string; ongoing: boolean }
export interface Decision { status: ReviewState; reason: string | null; remark: string | null; at: string | null; by?: string | null; follow_up_date: string | null; period_type: string; period_start: string }

export interface ZeroRow {
  store: { id: string; name: string; outlet_id: string; crm_code: string | null; region: string | null; platform: string | null; platform_slug: string | null; city: string | null; state: string | null };
  employees: Person[];
  longest: Streak | null;
  severity: Severity;
  total_zero: number;
  unmarked: number;
  last_nonzero: string | null;
  marked_by: { name: string | null; at: string | null } | null;
  flagged: boolean;
  status: ReviewState;
  review: Decision | null;
  total_orders: number;
  weekly?: Record<string, number>;
}

export interface StreaksResult {
  total: number; page: number; page_size: number; items: ZeroRow[];
  summary: { stores: number; with_zero_streak: number; ongoing: number; with_unmarked: number; pending: number };
  can_review: boolean; level: string; today: string; range: { from: string; to: string };
}

export interface WeeklyResult {
  week_start: string; week_end: string; threshold: number; is_current_default: boolean; today: string;
  summary: { flagged: number; reviewed: number; pending: number; complete: boolean };
  items: ZeroRow[]; markers: { name: string; stores: number; zero_days: number }[]; can_review: boolean; reasons: Reason[];
}

export interface MonthPeriod { month: string; start: string; end: string; closes_on: string; open: boolean; reopened: boolean; finished: boolean; days_left: number | null }
export interface Progress { name: string; total: number; verified: number; flagged: number }
export interface MonthlyResult {
  period: MonthPeriod; items: ZeroRow[]; can_review: boolean; can_reopen: boolean; is_admin: boolean;
  progress: { overall: { verified: number; flagged: number; total: number }; by_region: Progress[]; by_employee: Progress[] };
  reasons: Reason[];
}

export interface DayCell { date: string; kind: "zero" | "nonzero" | "unmarked" | "skip" | "future" | "holiday"; count: number | null; marked_by: string | null; marked_at: string | null; in_streak: boolean }
export interface StoreDays {
  store: { id: string; name: string; outlet_id: string }; days: DayCell[]; longest: Streak | null; total_zero: number; unmarked: number; last_nonzero: string | null;
  review: { status: ReviewState; reason: string | null; remark: string | null; at: string | null } | null;
}

export interface HistoryItem {
  id: string; at: string; event: string; from_status: string | null; to_status: string | null; period_type: "week" | "month"; period_start: string; period_end: string;
  store: { id: string; name: string; outlet_id: string } | null; threshold: number | null; longest_streak: number | null; reason: string | null; remark: string | null;
  follow_up_date: string | null; by: string | null; by_code: string | null;
}
export interface HistoryResult { total: number; page: number; page_size: number; items: HistoryItem[] }

/** The query string every Zero Review endpoint shares. Dates and the other filters are all validated again on the server. */
export function filterParams(f: ZeroFilterValues, extra: Record<string, string | number | undefined> = {}): URLSearchParams {
  const p = new URLSearchParams();
  if (f.from) p.set("date_from", f.from);
  if (f.to) p.set("date_to", f.to);
  f.regions.forEach((r) => p.append("region", r));
  f.employees.forEach((e) => p.append("employee", e));
  if (f.platform) p.set("platform", f.platform);
  if (f.q.trim()) p.set("search", f.q.trim());
  if (f.status) p.set("review_status", f.status);
  if (f.n) p.set("n", String(f.n));
  p.set("unmarked", f.unmarked);
  if (f.unmarkedGe) p.set("unmarked_ge", String(f.unmarkedGe));
  if (f.sort) p.set("sort", f.sort);
  for (const [k, v] of Object.entries(extra)) if (v !== undefined && v !== "") p.set(k, String(v));
  return p;
}

const get = <T,>(path: string) => apiRequest<T>(path, { silent: true });

export const useOptions = () => useQuery({ queryKey: ["zero", "options"], queryFn: () => get<Options>("/zero-review/options"), staleTime: 5 * 60_000 });

export const useBadge = (enabled: boolean) =>
  useQuery({ queryKey: ["zero", "badge"], queryFn: () => get<{ pending: number; weekly: number; months: number }>("/zero-review/badge"), enabled, staleTime: 5 * 60_000, refetchInterval: 10 * 60_000 });

export const useStreaks = (f: ZeroFilterValues, page: number, enabled = true) =>
  useQuery({ queryKey: ["zero", "streaks", f, page], queryFn: () => get<StreaksResult>(`/zero-review/streaks?${filterParams(f, { page, page_size: 50 })}`), enabled, placeholderData: keepPreviousData });

export const useStoreDays = (storeId: string | null, f: ZeroFilterValues) =>
  useQuery({ queryKey: ["zero", "days", storeId, f.from, f.to, f.n, f.unmarked], enabled: Boolean(storeId),
    queryFn: () => get<StoreDays>(`/zero-review/stores/${storeId}/days?${filterParams({ ...f, regions: [], employees: [], q: "", status: "", unmarkedGe: 0 })}`) });

export const useWeekly = (f: ZeroFilterValues, week: string, threshold: number, enabled = true) =>
  useQuery({ queryKey: ["zero", "weekly", f, week, threshold], enabled, placeholderData: keepPreviousData,
    queryFn: () => get<WeeklyResult>(`/zero-review/weekly?${filterParams({ ...f, from: "", to: "", n: 0 }, { week_start: week, threshold })}`) });

export const useMonthly = (f: ZeroFilterValues, month: string, enabled = true) =>
  useQuery({ queryKey: ["zero", "monthly", f, month], enabled, placeholderData: keepPreviousData,
    queryFn: () => get<MonthlyResult>(`/zero-review/monthly?${filterParams({ ...f, from: "", to: "", n: 0 }, { month })}`) });

export const useHistory = (f: ZeroFilterValues, page: number, extra: { reviewer: string; status: string; from: string; to: string }, enabled = true) =>
  useQuery({ queryKey: ["zero", "history", f, page, extra], enabled, placeholderData: keepPreviousData,
    queryFn: () => get<HistoryResult>(`/zero-review/history?${filterParams({ ...f, from: "", to: "", n: 0, status: "" }, { page, page_size: 50, reviewer: extra.reviewer, status: extra.status, period_from: extra.from, period_to: extra.to })}`) });

function useDone(message: string) {
  const qc = useQueryClient();
  return () => { void qc.invalidateQueries({ queryKey: ["zero"] }); pushToast(message, "success"); };
}
const fail = (e: unknown) => pushToast(e instanceof Error ? e.message : "That didn't work.", "error");

export function useReviewWeek() {
  const done = useDone("Marked reviewed. It is saved in the log.");
  return useMutation({
    mutationFn: (v: { week_start: string; store_ids: string[]; threshold: number; reason: string; remark: string; follow_up_date?: string }) =>
      apiRequest<{ reviewed: number }>("/zero-review/weekly/review", { method: "POST", silent: true, body: { ...v, follow_up_date: v.follow_up_date || null } }),
    onSuccess: done, onError: fail,
  });
}

export function useVerifyMonth() {
  const done = useDone("Saved. It is recorded in the log.");
  return useMutation({
    mutationFn: (v: { month: string; store_ids: string[]; status: "verified" | "flagged"; remark: string }) =>
      apiRequest<{ updated: number }>("/zero-review/monthly/verify", { method: "POST", silent: true, body: v }),
    onSuccess: done, onError: fail,
  });
}

export function useReopenMonth() {
  const done = useDone("The month is open again for a few days.");
  return useMutation({
    mutationFn: (v: { month: string; reason: string }) => apiRequest("/zero-review/monthly/reopen", { method: "POST", silent: true, body: v }),
    onSuccess: done, onError: fail,
  });
}

/** Downloads the current Zero Streaks result as a CSV file (opens in Excel). */
export async function downloadExport(f: ZeroFilterValues): Promise<void> {
  const blob = await apiBlob(`/zero-review/export?${filterParams(f)}`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `zero-review-${f.from}-${f.to}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
