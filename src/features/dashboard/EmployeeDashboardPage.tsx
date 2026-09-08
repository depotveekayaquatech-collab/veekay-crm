import { useEmployeeDashboard } from "@/features/dashboard/useDashboardData";
import { DemoDataBanner } from "@/components/feedback/DemoDataBanner";
import { Skeleton } from "@/components/feedback/Skeleton";
import { useAuth } from "@/features/auth/useAuth";

// Deliberately smaller than AdminDashboardPage: no regional performance,
// no other employees' names, no org-wide ticket volume — just this
// person's own work (spec section 10: "Employees should NOT see
// administrative information. They should only see data they are
// authorized to access.").
export function EmployeeDashboardPage() {
  const { user } = useAuth();
  const { data, isLoading } = useEmployeeDashboard();

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
        <Skeleton className="h-48" />
      </div>
    );
  }

  const { data: dashboard, isDemo } = data;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 sm:text-2xl">
          {user ? `Hi, ${user.fullName.split(" ")[0]}` : "Your day"}
        </h2>
        <p className="mt-1 text-sm text-gray-500">Here's what's on your plate today.</p>
      </div>

      {isDemo && <DemoDataBanner />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-surface-border bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-gray-500">Assigned today</p>
          <p className="mt-2 text-3xl font-semibold text-gray-900">{dashboard.assignedToday}</p>
        </div>
        <div className="rounded-lg border border-surface-border bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-gray-500">Completed</p>
          <p className="mt-2 text-3xl font-semibold text-status-success">{dashboard.completedToday}</p>
        </div>
        <div className="rounded-lg border border-surface-border bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-gray-500">Pending</p>
          <p className="mt-2 text-3xl font-semibold text-status-warning">{dashboard.pending}</p>
        </div>
      </div>

      <div className="rounded-lg border border-surface-border bg-white shadow-sm">
        <div className="border-b border-surface-border px-5 py-4">
          <h2 className="text-sm font-semibold text-gray-900">Your tickets</h2>
        </div>
        <div className="flex flex-col divide-y divide-surface-border px-5">
          {dashboard.tickets.length === 0 && <p className="py-6 text-sm text-gray-500">No open tickets right now.</p>}
          {dashboard.tickets.map((ticket) => (
            <div key={ticket.id} className="py-3">
              <p className="text-sm font-medium text-gray-900">{ticket.title}</p>
              <p className="text-xs text-gray-500">{ticket.region}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-surface-border bg-white shadow-sm">
        <div className="border-b border-surface-border px-5 py-4">
          <h2 className="text-sm font-semibold text-gray-900">Recent activity</h2>
        </div>
        <div className="flex flex-col divide-y divide-surface-border px-5">
          {dashboard.activity.map((item) => (
            <div key={item.time + item.text} className="py-3">
              <p className="text-sm text-gray-900">{item.text}</p>
              <p className="text-xs text-gray-500">{item.time}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
