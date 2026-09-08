import { useAuth } from "@/features/auth/useAuth";
import { AdminDashboardPage } from "@/features/dashboard/AdminDashboardPage";
import { EmployeeDashboardPage } from "@/features/dashboard/EmployeeDashboardPage";

// Roles decide which dashboard VARIANT renders — a UX choice, not a
// security boundary. The employee dashboard's own data still comes from
// a separate, narrower endpoint (/dashboard/employee) that the backend
// scopes to the caller; nothing here is what keeps an employee from
// seeing admin data (spec section 6: permissions, not roles, gate access).
const ADMIN_LIKE_ROLES = ["super_admin", "admin", "regional_manager", "blinkit_admin", "zepto_admin"];

export function DashboardPage() {
  const { hasRole } = useAuth();
  const isAdminLike = ADMIN_LIKE_ROLES.some((role) => hasRole(role));
  return isAdminLike ? <AdminDashboardPage /> : <EmployeeDashboardPage />;
}
