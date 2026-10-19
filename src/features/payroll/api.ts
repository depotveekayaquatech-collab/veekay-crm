import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";

export type PayMark = "FULL" | "HALF" | "ABSENT";
export type DayKind = "PRESENT" | "LEAVE" | "OFF" | "ABSENT" | "BEFORE_JOINING";
export type WindowState = "UPCOMING" | "OPEN" | "CLOSED";
export type PayStatus = "PAID" | "READY" | "NO_SALARY";

export interface PayPeriod {
  releaseDate: string;
  windowDays: number;
  closesOn: string;
  state: WindowState;
}

export interface PayrollRow {
  userId: string;
  employeeCode: string;
  fullName: string;
  categoryLabel: string;
  platform: string | null;
  region: string | null;
  isActive: boolean;
  monthlySalary: number | null;
  paidDays: number;
  amount: number | null;
  status: PayStatus;
  markedDays: number;
  absentDays: number;
  daysPresent: number;
  paidAt: string | null;
}

export interface PayrollOverview {
  month: string;
  monthLabel: string;
  months: string[];
  daysInMonth: number;
  today: string;
  period: PayPeriod;
  summary: { employees: number; paid: number; ready: number; noSalary: number; payableTotal: number; paidTotal: number };
  rows: PayrollRow[];
}

export interface PayDay {
  date: string;
  weekday: number;
  kind: DayKind;
  mark: PayMark | null;
  counted: number;
  default: number;
  checkInAt: string | null;
  checkOutAt: string | null;
  minutes: number;
  late: boolean;
  noCheckout: boolean;
  location: string | null;
  leaveType: string | null;
  halfDay: boolean;
}

export interface PayslipDetail {
  month: string;
  monthLabel: string;
  period: PayPeriod;
  daysInMonth: number;
  person: { userId: string; employeeCode: string; fullName: string };
  monthlySalary: number | null;
  perDay: number | null;
  days: PayDay[];
  paidDays: number;
  amount: number | null;
  status: PayStatus;
  payslip: { id: string; paidAt: string; paidBy: string | null } | null;
}

export interface MyPayslip {
  id: string;
  month: string;
  monthLabel: string;
  releaseDate: string;
  monthlySalary: number;
  daysInMonth: number;
  paidDays: number;
  amount: number;
  paidAt: string;
  seen: boolean;
  days?: PayDay[];
}

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
export const money = (v: number | null | undefined) => (v === null || v === undefined ? "—" : inr.format(v));
export const MARK_VALUE: Record<PayMark, number> = { FULL: 1, HALF: 0.5, ABSENT: 0 };

export function usePayroll(month: string) {
  return useQuery({
    queryKey: ["payroll", "overview", month],
    queryFn: async () => camelize<PayrollOverview>(await apiRequest(`/payroll${month ? `?month=${month}` : ""}`)),
  });
}

export function usePayslip(month: string, userId: string | null) {
  return useQuery({
    queryKey: ["payroll", "detail", month, userId],
    queryFn: async () => camelize<PayslipDetail>(await apiRequest(`/payroll/employees/${userId}?month=${month}`)),
    enabled: Boolean(userId && month),
  });
}

export function usePayrollMutations(month: string) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["payroll"] });
  return {
    period: useMutation({
      mutationFn: (v: { releaseDate: string; windowDays: number }) =>
        apiRequest(`/payroll/period?month=${month}`, { method: "PUT", body: { release_date: v.releaseDate, window_days: v.windowDays } }),
      onSuccess: () => {
        void refresh();
        pushToast("Payout date saved.", "success");
      },
    }),
    salary: useMutation({
      mutationFn: (v: { userId: string; monthlySalary: number | null }) =>
        apiRequest(`/payroll/salaries/${v.userId}`, { method: "PUT", body: { monthly_salary: v.monthlySalary } }),
      onSuccess: () => {
        void refresh();
        pushToast("Salary saved.", "success");
      },
    }),
    marks: useMutation({
      mutationFn: (v: { userId: string; marks: { date: string; mark: PayMark | null }[] }) =>
        apiRequest(`/payroll/employees/${v.userId}/marks?month=${month}`, { method: "PUT", body: { marks: v.marks } }),
      onSuccess: () => {
        void refresh();
        pushToast("Days saved.", "success");
      },
    }),
    pay: useMutation({
      mutationFn: (userId: string) => apiRequest(`/payroll/employees/${userId}/pay?month=${month}`, { method: "POST" }),
      onSuccess: () => {
        void refresh();
        pushToast("Marked as paid. The employee has been notified.", "success");
      },
    }),
  };
}

export function useMyPayslips(enabled = true) {
  return useQuery({
    queryKey: ["payroll", "me"],
    queryFn: async () => camelize<{ items: MyPayslip[] }>(await apiRequest("/payroll/me")),
    enabled,
  });
}

export function useUnseenPayslips() {
  return useQuery({
    queryKey: ["payroll", "unseen"],
    queryFn: async () => camelize<{ items: MyPayslip[] }>(await apiRequest("/payroll/me/unseen", { silent: true })),
    staleTime: 60_000,
    retry: false,
  });
}

export function useMarkPayslipSeen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiRequest(`/payroll/me/${id}/seen`, { method: "POST", silent: true }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["payroll", "unseen"] });
      void qc.invalidateQueries({ queryKey: ["payroll", "me"] });
    },
  });
}
