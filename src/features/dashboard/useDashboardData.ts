import { useQuery } from "@tanstack/react-query";
import { getAdminDashboard, getEmployeeDashboard } from "@/services/dashboard";
import { DEMO_ADMIN_DASHBOARD, DEMO_EMPLOYEE_DASHBOARD } from "@/features/dashboard/demoData";
import type { AdminDashboard, EmployeeDashboard } from "@/types/dashboard";

interface DashboardResult<T> {
  data: T;
  /** True when the real endpoint isn't reachable yet (not built, or a
   * genuine network failure) and we're showing demo data instead.
   * The page must render a visible "demo data" banner whenever this
   * is true — see AdminDashboardPage / EmployeeDashboardPage. */
  isDemo: boolean;
}

export function useAdminDashboard() {
  return useQuery<DashboardResult<AdminDashboard>>({
    queryKey: ["dashboard", "admin"],
    queryFn: async () => {
      try {
        return { data: await getAdminDashboard(), isDemo: false };
      } catch {
        return { data: DEMO_ADMIN_DASHBOARD, isDemo: true };
      }
    },
  });
}

export function useEmployeeDashboard() {
  return useQuery<DashboardResult<EmployeeDashboard>>({
    queryKey: ["dashboard", "employee"],
    queryFn: async () => {
      try {
        return { data: await getEmployeeDashboard(), isDemo: false };
      } catch {
        return { data: DEMO_EMPLOYEE_DASHBOARD, isDemo: true };
      }
    },
  });
}
