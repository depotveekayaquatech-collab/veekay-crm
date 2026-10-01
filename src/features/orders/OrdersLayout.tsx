import type { ComponentType, SVGProps } from "react";
import { Navigate, NavLink, Outlet } from "react-router-dom";
import { IconAlertTriangle, IconChart, IconClipboard, IconEdit } from "@/components/ui/icons";
import { useAuth } from "@/features/auth/useAuth";

interface OrderTab {
  label: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  permission: string;
  end?: boolean;
}

const ORDER_TABS: OrderTab[] = [
  { label: "Mark orders", to: "/orders", icon: IconClipboard, permission: "orders.view", end: true },
  { label: "Daily overview", to: "/orders/overview", icon: IconChart, permission: "orders.overview" },
  { label: "Pending entries", to: "/orders/pending", icon: IconAlertTriangle, permission: "orders.overview" },
  { label: "Correct entries", to: "/orders/correct", icon: IconEdit, permission: "orders.correct" },
];

/** One home for everything order-related: a header plus tabs (only the ones the user may open). */
export function OrdersLayout() {
  const { hasPermission } = useAuth();
  // People who can only look (e.g. partner accounts) get "Store entries" instead of "Mark orders".
  const tabs = ORDER_TABS.filter((t) => hasPermission(t.permission)).map((t) =>
    t.to === "/orders" && !hasPermission("orders.mark") ? { ...t, label: "Store entries" } : t,
  );
  if (tabs.length === 0) return <Navigate to="/" replace />;

  return (
    <div className="flex flex-col gap-5">
      <nav className="flex gap-1 overflow-x-auto rounded-xl border border-surface-border bg-white p-1.5 shadow-card" aria-label="Orders sections">
        {tabs.map((t) => {
          const Icon = t.icon;
          return (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
                  isActive ? "bg-brand-50 text-brand-700" : "text-gray-500 hover:bg-surface-subtle hover:text-gray-800"
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {t.label}
            </NavLink>
          );
        })}
      </nav>
      <Outlet />
    </div>
  );
}

/** "/orders" itself: Mark orders for people who can mark, otherwise the first tab they can open. */
export function OrdersIndex({ children }: { children: React.ReactNode }) {
  const { hasPermission } = useAuth();
  if (hasPermission("orders.view")) return <>{children}</>;
  const first = ORDER_TABS.find((t) => hasPermission(t.permission));
  return <Navigate to={first?.to ?? "/"} replace />;
}
