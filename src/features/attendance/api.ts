import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";

export interface LocationInfo {
  status: "office" | "outside" | "unknown";
  label: string;
  latitude?: number;
  longitude?: number;
  accuracyM?: number | null;
  distanceM?: number | null;
  mapUrl?: string;
}

/** PRESENT = marked present from an uploaded attendance sheet (no times were recorded). */
export type DayStatus = "CHECKED_IN" | "CHECKED_OUT" | "NO_CHECKOUT" | "PRESENT" | "ON_LEAVE" | "OFF" | "ABSENT";

export type StaffCategory = "admin" | "accounts" | "blinkit" | "zepto" | "other";

export interface Person {
  userId: string;
  employeeCode: string;
  fullName: string;
  roles: string[];
  platform: string | null;
  region: string | null;
  category: StaffCategory;
  categoryLabel: string;
}

export type LeaveType = "CASUAL" | "SICK" | "PAID" | "UNPAID";
export type LeaveStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";

export const LEAVE_LABEL: Record<LeaveType, string> = {
  CASUAL: "Casual leave",
  SICK: "Sick leave",
  PAID: "Paid leave",
  UNPAID: "Unpaid leave",
};

export const LEAVE_TONE: Record<LeaveStatus, "warning" | "success" | "danger" | "neutral"> = {
  PENDING: "warning",
  APPROVED: "success",
  REJECTED: "danger",
  CANCELLED: "neutral",
};

export interface DayRow extends Person {
  status: DayStatus;
  checkInAt: string | null;
  checkOutAt: string | null;
  minutes: number;
  late: boolean;
  halfDay?: boolean; // a developer marked this worked day as a half day (payroll counts 0.5)
  location: LocationInfo;
  checkOutLocation: LocationInfo | null;
  leaveType: LeaveType | null;
}

export interface RecordCorrection {
  user_id: string;
  work_date: string;
  check_in_time?: string; // also marks someone with no check-in present on that day
  check_out_time?: string;
  presence?: "office" | "away";
  late?: boolean;
  half_day?: boolean;
  clear_check_out?: boolean; // undo a check-out made by mistake
}

export interface DayOverview {
  date: string;
  isWeeklyOff: boolean;
  /** The company holiday on this date, if any (nobody is expected, so no one is marked absent). */
  holiday?: string | null;
  summary: {
    expected: number;
    present: number;
    checkedInNow: number;
    late: number;
    onLeave: number;
    absent: number;
    outsideOffice: number;
    locationUnknown: number;
  };
  rows: DayRow[];
}

export interface DayEntry {
  status: DayStatus;
  checkInAt: string | null;
  checkOutAt: string | null;
  minutes: number;
  late: boolean;
  location: LocationInfo;
  checkOutLocation?: LocationInfo | null;
  leaveType?: LeaveType;
  halfDay?: boolean;
}

export interface MonthRow extends Person {
  days: Record<string, DayEntry>;
  daysPresent: number;
  totalMinutes: number;
  outsideDays: number;
  lateDays: number;
  leaveDays: number;
  absentDays: number;
}

export interface MonthData {
  month: string;
  dates: string[];
  today: string;
  /** { "2026-11-01": "Diwali" }: the company holidays in this month. */
  holidays?: Record<string, string>;
  rows: MonthRow[];
}

export interface TodayStatus {
  eligible: boolean;
  date: string;
  workStart: string;
  graceMinutes: number;
  isWeeklyOff: boolean;
  checkedIn: boolean;
  checkedOut: boolean;
  checkInAt: string | null;
  checkOutAt: string | null;
  late: boolean;
  minutes: number | null;
  checkInLocation: LocationInfo | null;
  checkOutLocation: LocationInfo | null;
  onLeave: { leaveType: LeaveType; halfDay: boolean; endDate: string } | null;
}

export interface Leave {
  id: string;
  leaveType: LeaveType;
  startDate: string;
  endDate: string;
  halfDay: boolean;
  days: number;
  reason: string;
  status: LeaveStatus;
  createdAt: string;
  reviewedByName: string | null;
  reviewedAt: string | null;
  reviewNote: string | null;
  canCancel: boolean;
  person: { userId: string; name: string; code: string; platform: string | null; region: string | null } | null;
}

export interface OfficeInfo {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radiusM: number;
  isActive: boolean;
  mapUrl: string;
}

export function useTodayStatus() {
  return useQuery({
    queryKey: ["attendance", "today"],
    queryFn: async () => camelize<TodayStatus>(await apiRequest("/attendance/today", { silent: true })),
    staleTime: 15_000,
  });
}

export interface Reading {
  latitude?: number;
  longitude?: number;
  accuracy?: number;
}

export function useCheckMutations() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["attendance"] });
  return {
    checkIn: useMutation({
      mutationFn: async (r: Reading) => camelize<TodayStatus>(await apiRequest("/attendance/check-in", { method: "POST", body: r })),
      onSuccess: (t) => {
        qc.setQueryData(["attendance", "today"], t);
        refresh();
        pushToast(t.late ? "Checked in — you're marked late today." : "Checked in. Have a good day!", "success");
      },
    }),
    checkOut: useMutation({
      mutationFn: async (r: Reading) => camelize<TodayStatus>(await apiRequest("/attendance/check-out", { method: "POST", body: r })),
      onSuccess: (t) => {
        qc.setQueryData(["attendance", "today"], t);
        refresh();
        pushToast("Checked out. See you tomorrow!", "success");
      },
    }),
  };
}

/** Developer only (`attendance.edit`): fix a day's check-in time, office vs away, late and half day. */
export function useCorrectRecord() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: RecordCorrection) =>
      apiRequest("/attendance/record", { method: "PATCH", body: v }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["attendance"] });
      pushToast("Attendance updated.", "success");
    },
  });
}

export function useDayAttendance(date: string) {
  return useQuery({
    queryKey: ["attendance", "day", date],
    queryFn: async () => camelize<DayOverview>(await apiRequest(`/attendance/day?date=${date}`)),
    refetchInterval: 60_000, // "checked in now" stays fresh while the page is open
  });
}

export function useMonthAttendance(month: string, enabled = true) {
  return useQuery({
    queryKey: ["attendance", "month", month],
    queryFn: async () => camelize<MonthData>(await apiRequest(`/attendance/month?month=${month}`)),
    enabled,
  });
}

export function useMyAttendance(month: string, enabled = true) {
  return useQuery({
    queryKey: ["attendance", "me", month],
    queryFn: async () => camelize<MonthData>(await apiRequest(`/attendance/me?month=${month}`)),
    enabled,
  });
}

export function useMyLeaves(year: number, enabled = true) {
  return useQuery({
    queryKey: ["leave", "me", year],
    queryFn: async () =>
      camelize<{ year: number; items: Leave[]; taken: Record<LeaveType, number>; pending: number }>(
        await apiRequest(`/attendance/leaves/me?year=${year}`),
      ),
    enabled,
  });
}

export function useAllLeaves(status: string, q: string, enabled = true) {
  return useQuery({
    queryKey: ["leave", "all", status, q],
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (status) qs.set("status", status);
      if (q.trim()) qs.set("q", q.trim());
      return camelize<{ items: Leave[]; pending: number }>(await apiRequest(`/attendance/leaves?${qs}`));
    },
    enabled,
  });
}

export function useLeaveMutations() {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["leave"] });
    void qc.invalidateQueries({ queryKey: ["attendance"] });
  };
  return {
    apply: useMutation({
      mutationFn: (v: { leave_type: LeaveType; start_date: string; end_date: string; half_day: boolean; reason: string }) =>
        apiRequest("/attendance/leaves", { method: "POST", body: v }),
      onSuccess: () => {
        refresh();
        pushToast("Leave request sent for approval.", "success");
      },
    }),
    cancel: useMutation({
      mutationFn: (id: string) => apiRequest(`/attendance/leaves/${id}/cancel`, { method: "POST" }),
      onSuccess: () => {
        refresh();
        pushToast("Request cancelled.", "success");
      },
    }),
    review: useMutation({
      mutationFn: ({ id, approve, note }: { id: string; approve: boolean; note?: string }) =>
        apiRequest(`/attendance/leaves/${id}/review`, { method: "POST", body: { approve, note: note || null } }),
      onSuccess: (_d, v) => {
        refresh();
        pushToast(v.approve ? "Leave approved." : "Leave rejected.", "success");
      },
    }),
  };
}

export function useOffices(enabled = true) {
  return useQuery({
    queryKey: ["attendance", "offices"],
    queryFn: async () => camelize<OfficeInfo[]>(await apiRequest("/attendance/offices")),
    enabled,
  });
}

export interface HolidayInfo { date: string; name: string }

export function useHolidays(year: number, enabled = true) {
  return useQuery({ queryKey: ["attendance", "holidays", year], queryFn: () => apiRequest<HolidayInfo[]>(`/attendance/holidays?year=${year}`), enabled });
}

export function useHolidayMutations() {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["attendance"] });
    void qc.invalidateQueries({ queryKey: ["payroll"] });
    void qc.invalidateQueries({ queryKey: ["performance"] });
  };
  const add = useMutation({
    mutationFn: (v: { holiday_date: string; name: string }) => apiRequest("/attendance/holidays", { method: "POST", body: v, silent: true }),
    onSuccess: () => { refresh(); pushToast("Holiday saved. Nobody is counted absent that day.", "success"); },
    onError: (e) => pushToast(e instanceof Error ? e.message : "Could not save the holiday.", "error"),
  });
  const remove = useMutation({
    mutationFn: (day: string) => apiRequest<void>(`/attendance/holidays/${day}`, { method: "DELETE", silent: true }),
    onSuccess: () => { refresh(); pushToast("Holiday removed.", "success"); },
    onError: (e) => pushToast(e instanceof Error ? e.message : "Could not remove the holiday.", "error"),
  });
  return { add, remove };
}

export function useOfficeMutations() {
  const qc = useQueryClient();
  const done = (msg: string) => () => {
    void qc.invalidateQueries({ queryKey: ["attendance"] });
    pushToast(msg, "success");
  };
  const create = useMutation({
    mutationFn: (v: { name: string; latitude: number; longitude: number; radius_m?: number }) =>
      apiRequest("/attendance/offices", { method: "POST", body: v }),
    onSuccess: done("Office added."),
  });
  const update = useMutation({
    mutationFn: ({ id, ...v }: { id: string; name?: string; radius_m?: number; is_active?: boolean; latitude?: number; longitude?: number }) =>
      apiRequest(`/attendance/offices/${id}`, { method: "PATCH", body: v }),
    onSuccess: done("Office updated."),
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/attendance/offices/${id}`, { method: "DELETE" }),
    onSuccess: done("Office removed."),
  });
  return { create, update, remove };
}
