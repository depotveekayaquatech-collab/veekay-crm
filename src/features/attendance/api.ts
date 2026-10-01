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

export interface SessionInfo {
  id: string;
  loginAt: string;
  logoutAt: string | null;
  lastSeenAt: string;
  endedBy: "logout" | "revoked" | null;
  state: "active" | "idle" | "signed_out";
  ip: string | null;
  minutes: number;
  location: LocationInfo;
}

export type DayStatus = "ACTIVE" | "SIGNED_OUT" | "IDLE" | "ABSENT";

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

export interface DayRow extends Person {
  status: DayStatus;
  firstLogin: string | null;
  lastLogout: string | null;
  lastActive: string | null;
  minutes: number;
  signIns: number;
  location: LocationInfo;
  sessions: SessionInfo[];
}

export interface DayOverview {
  date: string;
  summary: { expected: number; present: number; activeNow: number; absent: number; outsideOffice: number; locationUnknown: number };
  rows: DayRow[];
}

export interface DayEntry {
  firstLogin: string;
  lastLogout: string | null;
  lastActive: string;
  minutes: number;
  signIns: number;
  status: DayStatus;
  location: LocationInfo;
  sessions?: SessionInfo[];
}

export interface MonthRow extends Person {
  days: Record<string, DayEntry>;
  daysPresent: number;
  totalMinutes: number;
  outsideDays: number;
}

export interface MonthData {
  month: string;
  dates: string[];
  today: string;
  rows: MonthRow[];
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

export function useDayAttendance(date: string) {
  return useQuery({
    queryKey: ["attendance", "day", date],
    queryFn: async () => camelize<DayOverview>(await apiRequest(`/attendance/day?date=${date}`)),
    refetchInterval: 60_000, // "active now" stays fresh while the page is open
  });
}

export function useMonthAttendance(month: string, enabled = true) {
  return useQuery({
    queryKey: ["attendance", "month", month],
    queryFn: async () => camelize<MonthData>(await apiRequest(`/attendance/month?month=${month}`)),
    enabled,
  });
}

export function useMyAttendance(month: string) {
  return useQuery({
    queryKey: ["attendance", "me", month],
    queryFn: async () => camelize<MonthData>(await apiRequest(`/attendance/me?month=${month}`)),
  });
}

export function useOffices(enabled = true) {
  return useQuery({
    queryKey: ["attendance", "offices"],
    queryFn: async () => camelize<OfficeInfo[]>(await apiRequest("/attendance/offices")),
    enabled,
  });
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
