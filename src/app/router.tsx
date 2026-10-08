import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { FullPageLoader } from "@/components/feedback/Skeleton";
import { OrdersIndex, OrdersLayout } from "@/features/orders/OrdersLayout";
import { ForcedPasswordChange } from "@/features/auth/ForcedPasswordChange";
import { useAuth } from "@/features/auth/useAuth";
import { usePermission } from "@/hooks/usePermission";

// Every page is its own chunk, fetched the first time it is opened — so the first load only carries the shell.
const HomePage = lazy(() => import("@/app/HomePage").then((m) => ({ default: m.HomePage })));
const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const LoginPage = lazy(() => import("@/features/auth/LoginPage").then((m) => ({ default: m.LoginPage })));
const MarkOrdersPage = lazy(() => import("@/features/orders/MarkOrdersPage").then((m) => ({ default: m.MarkOrdersPage })));
const DailyOverviewPage = lazy(() => import("@/features/orders/DailyOverviewPage").then((m) => ({ default: m.DailyOverviewPage })));
const CorrectEntriesPage = lazy(() => import("@/features/orders/CorrectEntriesPage").then((m) => ({ default: m.CorrectEntriesPage })));
const ReportsPage = lazy(() => import("@/features/reports/ReportsPage").then((m) => ({ default: m.ReportsPage })));
const AttendancePage = lazy(() => import("@/features/attendance/AttendancePage").then((m) => ({ default: m.AttendancePage })));
const AccountPage = lazy(() => import("@/features/account/AccountPage").then((m) => ({ default: m.AccountPage })));
const CardsPage = lazy(() => import("@/features/cards/CardsPage").then((m) => ({ default: m.CardsPage })));
const CountPage = lazy(() => import("@/features/cards/CountPage").then((m) => ({ default: m.CountPage })));
const CompliancePage = lazy(() => import("@/features/compliance/CompliancePage").then((m) => ({ default: m.CompliancePage })));
const CashPurchasesPage = lazy(() => import("@/features/cash/CashPurchasesPage").then((m) => ({ default: m.CashPurchasesPage })));
const DataSyncPage = lazy(() => import("@/features/datasync/DataSyncPage").then((m) => ({ default: m.DataSyncPage })));
const CashToolsPage = lazy(() => import("@/features/datasync/CashToolsPage").then((m) => ({ default: m.CashToolsPage })));
const AccountsPage = lazy(() => import("@/features/accounts/AccountsPage").then((m) => ({ default: m.AccountsPage })));
const InventoryPage = lazy(() => import("@/features/inventory/InventoryPage").then((m) => ({ default: m.InventoryPage })));
const PartnerHomePage = lazy(() => import("@/features/partner/PartnerHomePage").then((m) => ({ default: m.PartnerHomePage })));
const PartnerDeliveryReport = lazy(() => import("@/features/partner/PartnerDeliveryReport").then((m) => ({ default: m.PartnerDeliveryReport })));
const TicketsPage = lazy(() => import("@/features/tickets/TicketsPage").then((m) => ({ default: m.TicketsPage })));
const PendingPage = lazy(() => import("@/features/pending/PendingPage").then((m) => ({ default: m.PendingPage })));
const TeamPage = lazy(() => import("@/features/team/TeamPage").then((m) => ({ default: m.TeamPage })));
const StoresPage = lazy(() => import("@/features/stores/StoresPage").then((m) => ({ default: m.StoresPage })));
const ActivityPage = lazy(() => import("@/features/activity/ActivityPage").then((m) => ({ default: m.ActivityPage })));
const NotFoundPage = lazy(() => import("@/app/NotFoundPage").then((m) => ({ default: m.NotFoundPage })));

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

/** Like Require, but any one of the permissions is enough (hub pages with several audiences). */
function RequireAny({ permissions, children }: { permissions: string[]; children: React.ReactNode }) {
  const { hasPermission } = useAuth();
  return permissions.some(hasPermission) ? <>{children}</> : <Navigate to="/" replace />;
}

/** "/" — the dashboard for staff; a partner login (Blinkit / Zepto) gets its own portal home. */
function HomeRoute() {
  const { user } = useAuth();
  // A developer account has no business pages at all, only the sheet tools.
  if (user?.roles.includes("developer") && !user.roles.includes("admin")) return <Navigate to="/data-sync" replace />;
  return user?.roles.includes("partner") ? <PartnerHomePage /> : <DashboardPage />;
}

function LoginRoute() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <FullPageLoader />;
  if (user) return <Navigate to="/" replace />;
  return <LoginPage />;
}

export function AppRoutes() {
  return (
    <Suspense fallback={<FullPageLoader />}>
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
        <Route path="/" element={<HomeRoute />} />
        <Route path="/delivery-reports" element={<Require permission="reports.delivery"><PartnerDeliveryReport /></Require>} />
        <Route path="/tickets" element={<RequireAny permissions={["tickets.view", "tickets.manage"]}><TicketsPage /></RequireAny>} />
        <Route path="/orders" element={<OrdersLayout />}>
          <Route index element={<OrdersIndex><MarkOrdersPage /></OrdersIndex>} />
          <Route path="overview" element={<Require permission="orders.overview"><DailyOverviewPage /></Require>} />
          <Route path="pending" element={<Require permission="orders.overview"><PendingPage /></Require>} />
          <Route path="correct" element={<Require permission="orders.correct"><CorrectEntriesPage /></Require>} />
        </Route>
        <Route path="/attendance" element={<AttendancePage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/cards" element={<Require permission="orders.view"><CardsPage /></Require>} />
        <Route path="/compliance" element={<Require permission="compliance.upload"><CompliancePage /></Require>} />
        <Route path="/cash" element={<RequireAny permissions={["cash.view", "cash.add"]}><CashPurchasesPage /></RequireAny>} />
        <Route path="/data-sync" element={<Require permission="sheets.sync"><DataSyncPage /></Require>} />
        <Route path="/developer/cash" element={<Require permission="cash.adjust"><CashToolsPage /></Require>} />
        <Route path="/accounts" element={<Require permission="accounts.view"><AccountsPage /></Require>} />
        <Route path="/inventory" element={<Require permission="orders.view"><InventoryPage /></Require>} />
        <Route path="/pending" element={<Navigate to="/orders/pending" replace />} />
        <Route path="/reports" element={<Require permission="orders.overview"><ReportsPage /></Require>} />
        <Route path="/team" element={<Require permission="employees.view"><TeamPage /></Require>} />
        <Route path="/stores" element={<Require permission="stores.view"><StoresPage /></Require>} />
        <Route path="/regions" element={<Navigate to="/stores" replace />} />
        <Route path="/activity" element={<Require permission="activity.view"><ActivityPage /></Require>} />
      </Route>
      <Route path="/home" element={<HomePage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
    </Suspense>
  );
}
