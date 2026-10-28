/** Admin and reporting endpoints (the same ones the web dashboard uses), plus sheet-sync status. */
import { request } from "@/api/client";
import type { LeaveItem } from "@/api/staff";

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface SyncStatus {
  schedule: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_source: "scheduled" | "manual" | null;
  last_run_by: string | null;
  last_run_warnings: number | null;
  stores_sheets: number;
  orders_sheets: number;
  can_sync: boolean;
}

export interface Insights {
  bottles_today: number;
  bottles_yesterday: number;
  entries_today: number;
  store_status: Record<string, number>;
  trend: { date: string; label: string; entries: number; bottles: number }[];
  platforms: { slug: string; label: string; total_stores: number; entries_done: number; bottles: number; percent: number }[];
  attention_stores: { id: string; name: string; external_code: string; platform: string | null; city: string | null; state: string | null }[];
  dormant_live: number;
  last_store_sync: string | null;
}

export interface PendingStore {
  id: string; name: string; external_code: string; platform: string | null; region_name: string | null; state: string | null;
  city: string | null; vendor_name: string | null; poc_name: string | null; poc_number: string | null; pending_days: number;
}
export interface PendingEntries { date: string; date_label: string; day_offset: number; live_stores: number; marked: number; pending: number; items: PendingStore[] }

export interface LeaveAdminItem extends LeaveItem { person: { name: string; code: string; platform: string | null; region: string | null } | null }
export interface LeavesAll { items: LeaveAdminItem[]; pending: number }

export interface BottleSummary { total_active: number; at_store: number; overdue: number; lost_after_days: number }
export interface OverdueBottle { serial: string; store_name: string | null; last_in_at: string | null; days_at_store: number | null }
export interface OverdueList { items: OverdueBottle[]; total: number; page: number; page_size: number }

export interface DueBill { id: string; store_name: string; external_code: string; platform: string | null; state: string | null; vendor_name: string | null; month: string; due_date: string; days_overdue: number }
export interface DueBills { total: number; items: DueBill[] }

export type AttendanceStatus = "CHECKED_IN" | "CHECKED_OUT" | "NO_CHECKOUT" | "PRESENT" | "ON_LEAVE" | "OFF" | "ABSENT";
export interface AttendanceDayRow {
  user_id: string; employee_code: string; full_name: string; platform: string | null; region: string | null; category: string; category_label: string;
  status: AttendanceStatus; check_in_at: string | null; check_out_at: string | null; minutes: number; late: boolean; leave_type: string | null;
  location: { status: string; label: string };
}
export interface AttendanceDay {
  date: string; is_weekly_off: boolean; holiday?: string | null;
  summary: { expected: number; present: number; checked_in_now: number; late: number; on_leave: number; absent: number; outside_office: number; location_unknown: number };
  rows: AttendanceDayRow[];
}
export interface AttendanceMonthRow {
  user_id: string; employee_code: string; full_name: string; platform: string | null; region: string | null; category: string; category_label: string;
  present_dates: string[]; leave_dates: string[]; days_present: number; late_days: number; leave_days: number; absent_days: number;
}
export interface AttendanceMonth { month: string; dates: string[]; today: string; weekly_off_weekday: number; holidays?: Record<string, string>; rows: AttendanceMonthRow[] }

export interface PerformanceDay { date: string; done: number; expected: number; percent: number; cumulative: number }
export interface PerformanceRow {
  employee_id: string; employee_code: string; employee_name: string; region_name: string | null;
  stores: number; expected: number; done: number; missing: number; percent: number; daily: PerformanceDay[];
  /** Everything this person entered on the platform this month, in any store. */
  entries_made?: number;
  /** No store of their own: no percentage, only the entries they made. */
  no_stores?: boolean;
  /** Entries whose number this person changed this month (a Team Lead's job). */
  corrected?: number;
  is_team_lead?: boolean;
}
export interface Performance {
  partner_slug: string; partner_label: string; month: string; month_label: string; from: string | null; as_of: string | null; days: number;
  summary: { employees: number; expected: number; done: number; percent: number; below_50: number };
  employees: PerformanceRow[];
}

export interface VendorStoreRow { store_id: string; store_name: string; external_code: string; city: string | null; state: string | null; live: boolean; bottles: number; days_marked: number }
export interface VendorRow { vendor_name: string | null; vendor_number: string | null; store_count: number; bottles: number; stores: VendorStoreRow[] }
export interface VendorPerformance {
  partner_slug: string; partner_label: string; month: string; month_label: string; from: string | null; to: string | null;
  summary: { vendors: number; stores: number; bottles: number };
  vendors: VendorRow[];
}

export interface MarkDaysResult { marked: number; already_present: number; removed: number; kept_real_check_ins: string[] }

export const adminApi = {
  markDays: (userId: string, dates: string[], present: boolean) =>
    request<MarkDaysResult>("/attendance/mark", { method: "POST", body: { user_id: userId, dates, present } }),
  performance: (partner: string, month: string) => request<Performance>(`/orders/performance${qs({ partner, month })}`),
  vendorPerformance: (partner: string, month: string) => request<VendorPerformance>(`/orders/performance/vendors${qs({ partner, month })}`),
  attendanceDay: () => request<AttendanceDay>("/attendance/day"),
  attendanceMonth: (month: string) => request<AttendanceMonth>(`/attendance/month-brief${qs({ month })}`),
  syncStatus: () => request<SyncStatus>("/sync/status"),
  syncRun: () => request<{ stores: { platform: string; created: number; updated: number }[]; orders: { platform: string; created: number; updated: number }[] }>("/sync/run", { method: "POST", body: {} }),
  insights: () => request<Insights>("/orders/insights"),
  pending: (dayOffset: number) => request<PendingEntries>(`/orders/pending${qs({ day_offset: dayOffset })}`),
  leaves: (status: string) => request<LeavesAll>(`/attendance/leaves${qs({ status })}`),
  reviewLeave: (id: string, approve: boolean, note: string) =>
    request<LeaveAdminItem>(`/attendance/leaves/${id}/review`, { method: "POST", body: { approve, note: note || null } }),
  bottleSummary: () => request<BottleSummary>("/bottles/summary"),
  overdueBottles: (page: number) => request<OverdueList>(`/bottles${qs({ state: "OVERDUE", page, page_size: 50 })}`),
  dueBills: () => request<DueBills>("/compliance/due"),
};
