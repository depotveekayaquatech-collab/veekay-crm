import { apiRequest } from "@/services/api";
import type { AdminDashboard, EmployeeDashboard } from "@/types/dashboard";

// These hit real endpoints per spec section 20 (one aggregated call each,
// not a dozen sequential requests). They don't exist on the backend yet —
// that's Phase 3 (Orders) + Phase 4 (Tickets) work, since the dashboard
// aggregates both. Until then these calls 404, and the hooks in
// features/dashboard/ fall back to demo data with a visible banner
// (see useDashboardData.ts) rather than silently showing fake numbers
// as if they were real (spec section 43).

export function getAdminDashboard(): Promise<AdminDashboard> {
  return apiRequest<AdminDashboard>("/dashboard/admin", { silent: true });
}

export function getEmployeeDashboard(): Promise<EmployeeDashboard> {
  return apiRequest<EmployeeDashboard>("/dashboard/employee", { silent: true });
}
