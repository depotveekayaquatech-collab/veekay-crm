import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { FullPageLoader } from "@/components/feedback/Skeleton";
import { HomePage } from "@/app/HomePage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { MarkOrdersPage } from "@/features/orders/MarkOrdersPage";
import { DailyOverviewPage } from "@/features/orders/DailyOverviewPage";
import { CorrectEntriesPage } from "@/features/orders/CorrectEntriesPage";
import { ReportsPage } from "@/features/reports/ReportsPage";
import { AttendancePage } from "@/features/attendance/AttendancePage";
import { AccountPage } from "@/features/account/AccountPage";
import { ForcedPasswordChange } from "@/features/auth/ForcedPasswordChange";
import { CardsPage } from "@/features/cards/CardsPage";
import { CountPage } from "@/features/cards/CountPage";
import { CompliancePage } from "@/features/compliance/CompliancePage";
import { AccountsPage } from "@/features/accounts/AccountsPage";
import { InventoryPage } from "@/features/inventory/InventoryPage";
import { PendingPage } from "@/features/pending/PendingPage";
import { TeamPage } from "@/features/team/TeamPage";
import { StoresPage } from "@/features/stores/StoresPage";
import { RegionsPage } from "@/features/regions/RegionsPage";
import { ActivityPage } from "@/features/activity/ActivityPage";
import { NotFoundPage } from "@/app/NotFoundPage";
import { useAuth } from "@/features/auth/useAuth";
import { usePermission } from "@/hooks/usePermission";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" replace />;
  // A temporary / admin-set password must be replaced before anything else is usable.
  if (user.mustChangePassword) return <ForcedPasswordChange />;
  return <>{children}</>;
}

/** Route-level permission gate — the backend is still the real guard. */
function Require({ permission, children }: { permission: string; children: React.ReactNode }) {
  return usePermission(permission) ? <>{children}</> : <Navigate to="/" replace />;
}

function LoginRoute() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <FullPageLoader />;
  if (user) return <Navigate to="/" replace />;
  return <LoginPage />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/count" element={<CountPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/orders" element={<Require permission="orders.mark"><MarkOrdersPage /></Require>} />
        <Route path="/orders/overview" element={<Require permission="orders.overview"><DailyOverviewPage /></Require>} />
        <Route path="/orders/correct" element={<Require permission="orders.correct"><CorrectEntriesPage /></Require>} />
        <Route path="/attendance" element={<AttendancePage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/cards" element={<Require permission="orders.view"><CardsPage /></Require>} />
        <Route path="/compliance" element={<Require permission="compliance.upload"><CompliancePage /></Require>} />
        <Route path="/accounts" element={<Require permission="accounts.view"><AccountsPage /></Require>} />
        <Route path="/inventory" element={<Require permission="orders.view"><InventoryPage /></Require>} />
        <Route path="/pending" element={<Require permission="orders.overview"><PendingPage /></Require>} />
        <Route path="/reports" element={<Require permission="orders.overview"><ReportsPage /></Require>} />
        <Route path="/team" element={<Require permission="employees.view"><TeamPage /></Require>} />
        <Route path="/stores" element={<Require permission="stores.view"><StoresPage /></Require>} />
        <Route path="/regions" element={<Require permission="regions.view"><RegionsPage /></Require>} />
        <Route path="/activity" element={<Require permission="activity.view"><ActivityPage /></Require>} />
      </Route>
      <Route path="/home" element={<HomePage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
