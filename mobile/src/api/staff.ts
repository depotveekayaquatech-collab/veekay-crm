/** Veekay employee endpoints (the same API the web app uses). Shapes are kept as the API sends them. */
import { adoptTokens, request } from "@/api/client";

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
  platform_label: string | null;
  region_name: string | null;
  permissions: string[];
  roles: string[];
  is_admin: boolean;
  must_change_password: boolean;
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

export type LeaveType = "CASUAL" | "SICK" | "PAID" | "UNPAID";
export interface LeaveItem {
  id: string; leave_type: LeaveType; start_date: string; end_date: string; half_day: boolean; days: number; reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED"; created_at: string; reviewed_by_name: string | null;
  review_note: string | null; can_cancel: boolean;
}
export interface LeavesMe { year: number; items: LeaveItem[]; taken: Record<string, number>; pending: number }

export interface MyStore {
  id: string; name: string; external_code: string; state: string | null; city: string | null; region_name: string | null;
  status: string; partner_name: string | null; today: string; today_count: number | null;
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
export interface CashOptions {
  office_reasons: Reason[];
  store_reasons: Reason[];
  stores: { id: string; name: string; code: string; platform: string | null; state: string | null }[];
  can_view_all: boolean;
  max_amount: string | number;
}
export interface CashPurchase {
  id: string; kind: "OFFICE" | "STORE"; purchase_date: string; store_name: string | null; category_label: string;
  other_reason: string | null; amount: string | number; notes: string | null; has_proof: boolean; created_at: string;
}
export interface CashList { items: CashPurchase[]; total: number; page: number; page_size: number; amount_total: string | number }

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

  leaves: () => request<LeavesMe>("/attendance/leaves/me"),
  applyLeave: (b: { leave_type: LeaveType; start_date: string; end_date: string; half_day: boolean; reason: string }) =>
    request<LeaveItem>("/attendance/leaves", { method: "POST", body: b }),
  cancelLeave: (id: string) => request<LeaveItem>(`/attendance/leaves/${id}/cancel`, { method: "POST", body: {} }),

  myStores: () => request<MyStore[]>("/orders/my-stores"),
  markOrder: (b: { store_id: string; order_date: string; bottle_count: number }) => request<unknown>("/orders/mark", { method: "POST", body: b }),

  scanStores: () => request<ScanStore[]>("/bottles/stores"),
  scan: (b: ScanBody) => request<ScanResult>("/bottles/scan", { method: "POST", body: b }),

  cashOptions: () => request<CashOptions>("/cash-purchases/options"),
  cashList: (p: { page?: number; page_size?: number }) => request<CashList>(`/cash-purchases${qs(p)}`),
  addCash: (form: FormData, key?: string) => request<CashPurchase>("/cash-purchases", { method: "POST", body: form, idempotencyKey: key }),

  alerts: (page = 1) => request<StaffAlertPage>(`/me/notifications${qs({ page, page_size: 50 })}`),
  markAlertsRead: (ids?: string[]) => request<void>("/me/notifications/read", { method: "POST", body: ids ? { ids } : {} }),
  registerDevice: (token: string) => request<void>("/me/devices", { method: "POST", body: { token, platform: "android" } }),
  unregisterDevice: (token: string) => request<void>(`/me/devices${qs({ token })}`, { method: "DELETE" }),
};
