import { Suspense, useEffect, type ComponentType, type SVGProps } from "react";
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { IconAlertTriangle, IconChart, IconClipboard, IconEdit } from "@/components/ui/icons";
import { useAuth } from "@/features/auth/useAuth";
import { usePending } from "@/services/reports";

interface OrderTab {
  label: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  permission: string;
  blurb: string;
  end?: boolean;
}

const ORDER_TABS: OrderTab[] = [
  { label: "Mark orders", to: "/orders", icon: IconClipboard, permission: "orders.view", end: true, blurb: "Log each store's daily bottle count." },
  { label: "Daily overview", to: "/orders/overview", icon: IconChart, permission: "orders.overview", blurb: "See how every employee is tracking today." },
  { label: "Pending entries", to: "/orders/pending", icon: IconAlertTriangle, permission: "orders.overview", blurb: "Live stores that still have no entry." },
  { label: "Correct entries", to: "/orders/correct", icon: IconEdit, permission: "orders.correct", blurb: "Fix or clear any past day for any store." },
];

/** Red count on the "Pending entries" tab, so admins see the backlog without opening it. */
function PendingCount() {
  const { data } = usePending(0, "");
  if (!data || data.pending === 0) return null;
  return (
    <span className="ml-0.5 rounded-full bg-status-danger px-1.5 py-px text-[11px] font-bold tabular-nums text-white" aria-label={`${data.pending} pending`}>
      {data.pending > 99 ? "99+" : data.pending}
    </span>
  );
}

/** One home for everything order-related: a hero header plus tabs (only the ones the user may open). */
export function OrdersLayout() {
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  // People who can only look (e.g. partner accounts) get "Store entries" instead of "Mark orders".
  const tabs = ORDER_TABS.filter((t) => hasPermission(t.permission)).map((t) =>
    t.to === "/orders" && !hasPermission("orders.mark") ? { ...t, label: "Store entries", blurb: "Browse each store's daily entries." } : t,
  );

  // Press 1–4 to jump between tabs (ignored while typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
      const tab = tabs[Number(e.key) - 1];
      if (tab) navigate(tab.to);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (tabs.length === 0) return <Navigate to="/" replace />;

  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="flex flex-col gap-6">
      <header className="relative overflow-hidden rounded-2xl border border-surface-border bg-surface p-5 shadow-card sm:p-6">
        <span aria-hidden="true" className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-gradient-to-br from-brand-500/20 to-aqua-400/10 blur-2xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-brand-600">{today}</p>
            <h2 className="mt-1 text-2xl font-extrabold text-heading sm:text-[1.75rem]">Orders</h2>
            <p className="mt-1 text-sm text-gray-500">Record, review and correct daily bottle counts across every store.</p>
          </div>
        </div>

        <nav className="relative -mb-1 mt-5 flex gap-1 overflow-x-auto pb-1" aria-label="Orders sections">
          {tabs.map((t, i) => {
            const Icon = t.icon;
            return (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                title={`${t.blurb} (press ${i + 1})`}
                className={({ isActive }) =>
                  `group flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-[color,background-color,box-shadow] ${
                    isActive
                      ? "bg-gradient-to-b from-[rgb(var(--btn-a))] to-[rgb(var(--btn-b))] text-white shadow-glow"
                      : "text-gray-600 hover:bg-surface-muted hover:text-gray-900"
                  }`
                }
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {t.label}
                {t.to === "/orders/pending" && <PendingCount />}
                <kbd className="ml-0.5 hidden rounded border border-current/20 px-1 text-[10px] font-semibold opacity-60 lg:inline">{i + 1}</kbd>
              </NavLink>
            );
          })}
        </nav>
      </header>
      <Suspense fallback={<div className="h-64 animate-pulse rounded-2xl bg-surface-border/40" aria-busy="true" />}>
        <Outlet />
      </Suspense>
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
