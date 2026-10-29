/** Veekay employee endpoints (the same API the web app uses). Shapes are kept as the API sends them. */
import { adoptTokens, request } from "@/api/client";
import type { EntryChange, EntryStatus } from "@/lib/format";

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface StaffMe {
  id: string;
  employee_code: string;
  full_name: string;
  email: string | null;
  platform_slug?: string | null;
  platform_label: string | null;
  region_name: string | null;
  permissions: string[];
  roles: string[];
  is_admin: boolean;
  must_change_password: boolean;
  /** The server lets you change an entry you already saved (off by default: a Team Lead or an admin corrects it). */
  can_correct_own_entries?: boolean;
  /** Given the permission to change ANY earlier entry of their stores (whoever entered it), in the dates still open: this month, and last month for the first 5 days. */
  can_edit_previous?: boolean;
  /** entry_contributor | team_lead | entry_reviewer | administrator */
  entry_level?: string;
}

export interface AttendanceToday {
  eligible: boolean;
  date: string;
  work_start: string;
  is_weekly_off: boolean;
  checked_in: boolean;
  checked_out: boolean;
  check_in_at: string | null;
  check_out_at: string | null;
  late: boolean;
  minutes: number | null;
  check_in_location: { status?: string; label?: string | null; distance_m?: number | null } | null;
  check_out_location: { status?: string; label?: string | null; distance_m?: number | null } | null;
  on_leave: { leave_type: string; half_day: boolean } | null;
}

export interface Reading { latitude?: number; longitude?: number; accuracy?: number }

/** One entry the signed-in employee saved, with the status its store has today. */
export interface MyEntry {
  order_date: string; store_id: string; store_name: string; store_code: string; city: string | null; state: string | null;
  store_status: string; bottles: number; source: string; entered_at: string;
  /** The server's own record of this entry. */
  entry_id?: string; version?: number; saved_on_server?: boolean; corrected?: boolean;
  /** Where it stands in the verification workflow, and who changed the number after it was saved. */
  verification?: EntryStatus | null; changed?: EntryChange | null;
}
export interface MyEntries { today: string; days: number; total: number; items: MyEntry[] }

export type LeaveType = "CASUAL" | "SICK" | "PAID" | "UNPAID";
export interface LeaveItem {
  id: string; leave_type: LeaveType; start_date: string; end_date: string; half_day: boolean; days: number; reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED"; created_at: string; reviewed_by_name: string | null;
  review_note: string | null; can_cancel: boolean;
}
export interface LeavesMe { year: number; items: LeaveItem[]; taken: Record<string, number>; pending: number }

export interface PayslipDay {
  date: string; kind: "PRESENT" | "LEAVE" | "OFF" | "ABSENT" | "BEFORE_JOINING"; mark: "FULL" | "HALF" | "ABSENT" | null; counted: number;
  check_in_at: string | null; check_out_at: string | null; minutes: number; late: boolean; no_checkout: boolean; location: string | null;
  leave_type: string | null; half_day: boolean;
}
export interface Payslip {
  id: string; month: string; month_label: string; release_date: string; monthly_salary: number; days_in_month: number; paid_days: number;
  amount: number; paid_at: string; seen: boolean; days?: PayslipDay[];
}

export interface MyStore {
  id: string; name: string; external_code: string;
  /** The store's permanent system code (BKT000123 / ZPT000045), and whether another store of this platform has exactly this name. */
  crm_code?: string | null; duplicate_name?: boolean; state: string | null; city: string | null; region_name: string | null; vendor_name: string | null;
  /** The vendor's phone and the store's point of contact, as the store sheet has them. */
  vendor_number?: string | null; poc_name?: string | null; poc_number?: string | null;
  status: string; partner_name: string | null; today: string;
  /** YOUR number for the day (null when you have not marked it, or a colleague did). */
  today_count: number | null; yesterday_count?: number | null;
  /** What a Team Lead / Reviewer did to YOUR number after you saved it: who (name and role), when, old and new. */
  today_changed?: EntryChange | null; yesterday_changed?: EntryChange | null;
  /** Somebody (you or a colleague) marked the day. */
  today_marked?: boolean; yesterday_marked?: boolean;
  /** Days up to yesterday with no entry since the store's last filled day this month (0: only today is still due). */
  pending_days?: number;
  /** Bottles marked for this store so far this month, and in the whole of last month. */
  month_bottles?: number;
  last_month_bottles?: number;
  /** While last month can still be marked (the first days of a month): its days with no entry yet, and the last day it stays open. */
  last_month_missing?: number;
  last_month_open_until?: string | null;
}

export type Direction = "IN" | "OUT";
export interface ScanBody { serial: string; direction: Direction; store_id?: string | null; scanned_at?: string; scan_id: string }
export interface ScanResult {
  duplicate: boolean;
  warning: string | null;
  bottle: { serial: string; status: string; store_name: string | null };
  scan: { direction: Direction; store_name: string | null };
}
export interface ScanStore { id: string; name: string; code: string; city: string | null }

export interface Reason { code: string; label: string }

/** An earlier purchase that looks like the one being added (the server's POSSIBLE_DUPLICATE answer). */
export interface DuplicateMatch {
  id: string; purchase_date: string; amount: string; kind: string; store_name: string | null; category_label: string;
  added_by: string; created_at: string; same_details: boolean; same_file: boolean;
}
export interface DuplicateAnswer { code: "POSSIBLE_DUPLICATE"; message: string; matches: DuplicateMatch[] }
export interface CashOptions {
  office_reasons: Reason[];
  store_reasons: Reason[];
  stores: { id: string; name: string; code: string; platform: string | null; state: string | null }[];
  can_view_all: boolean;
  max_amount: string | number;
}
export interface CashPurchase {
  id: string; kind: "OFFICE" | "STORE"; purchase_date: string; store_name: string | null; category_label: string;
  other_reason: string | null; amount: string | number; notes: string | null; has_proof: boolean; added_by?: string | null; created_at: string;
}
export interface CashList { items: CashPurchase[]; total: number; page: number; page_size: number; amount_total: string | number; office_total: string | number; store_total: string | number }
export type CashFilter = { kind?: "OFFICE" | "STORE"; start?: string; end?: string };

export interface StaffAlert { id: string; kind: string; title: string; body: string; ref_id: string | null; read: boolean; created_at: string }
export interface StaffAlertPage { items: StaffAlert[]; total: number; unread: number; page: number; page_size: number }

export const staffApi = {
  me: () => request<StaffMe>("/auth/me"),
  /** Replaces a temporary password. Every other device is signed out; this one gets a fresh session. */
  async changePassword(current: string, next: string): Promise<void> {
    const pair = await request<{ access_token: string; refresh_token: string }>("/auth/change-password", {
      method: "POST", body: { current_password: current, new_password: next },
    });
    await adoptTokens(pair);
  },

  attendanceToday: () => request<AttendanceToday>("/attendance/today"),
  checkIn: (r: Reading) => request<unknown>("/attendance/check-in", { method: "POST", body: r }),
  checkOut: (r: Reading) => request<unknown>("/attendance/check-out", { method: "POST", body: r }),

  payslips: () => request<{ items: Payslip[] }>("/payroll/me"),
  unseenPayslips: () => request<{ items: Payslip[] }>("/payroll/me/unseen"),
  payslipSeen: (id: string) => request<{ id: string; seen: boolean }>(`/payroll/me/${id}/seen`, { method: "POST", body: {} }),

  leaves: () => request<LeavesMe>("/attendance/leaves/me"),
  applyLeave: (b: { leave_type: LeaveType; start_date: string; end_date: string; half_day: boolean; reason: string }) =>
    request<LeaveItem>("/attendance/leaves", { method: "POST", body: b }),
  cancelLeave: (id: string) => request<LeaveItem>(`/attendance/leaves/${id}/cancel`, { method: "POST", body: {} }),

  myStores: () => request<MyStore[]>("/orders/my-stores"),
  myEntries: (days: number) => request<MyEntries>(`/orders/my-entries?days=${days}`),
  markOrder: (b: { store_id: string; order_date: string; bottle_count: number }) => request<unknown>("/orders/mark", { method: "POST", body: b }),

  scanStores: () => request<ScanStore[]>("/bottles/stores"),
  scan: (b: ScanBody) => request<ScanResult>("/bottles/scan", { method: "POST", body: b }),

  cashOptions: () => request<CashOptions>("/cash-purchases/options"),
  cashList: (p: { page?: number; page_size?: number } & CashFilter) => request<CashList>(`/cash-purchases${qs(p)}`),
  /** Path of the Excel sheet for the same filters (needs the cash.view permission; the server enforces it). */
  cashSheetPath: (f: CashFilter) => `/cash-purchases/export${qs(f)}`,
  addCash: (form: FormData, key?: string) => request<CashPurchase>("/cash-purchases", { method: "POST", body: form, idempotencyKey: key }),

  alerts: (page = 1) => request<StaffAlertPage>(`/me/notifications${qs({ page, page_size: 50 })}`),
  markAlertsRead: (ids?: string[]) => request<void>("/me/notifications/read", { method: "POST", body: ids ? { ids } : {} }),
  registerDevice: (token: string) => request<void>("/me/devices", { method: "POST", body: { token, platform: "android" } }),
  unregisterDevice: (token: string) => request<void>(`/me/devices${qs({ token })}`, { method: "DELETE" }),
};
