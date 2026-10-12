import { useEffect } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { FullPageLoader } from "@/components/feedback/Skeleton";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { IconActivity, IconBox, IconClipboard, IconGrid, IconTicket } from "@/components/ui/icons";
import { niceName } from "@/features/vendor/format";
import { useVendorAuth } from "@/features/vendor/vendor-auth-context";
import { useNotifications } from "@/features/vendor/useVendorData";

/** Makes the /vendor pages installable ("Add to home screen") without touching the staff app. */
function usePwa() {
  useEffect(() => {
    const link = document.createElement("link");
    link.rel = "manifest";
    link.href = "/vendor/manifest.webmanifest";
    document.head.appendChild(link);
    if ("serviceWorker" in navigator && import.meta.env.PROD) {
      navigator.serviceWorker.register("/vendor/sw.js", { scope: "/vendor/" }).catch(() => undefined);
    }
    return () => link.remove();
  }, []);
}

function Tab({ to, label, icon, end, badge }: { to: string; label: string; icon: React.ReactNode; end?: boolean; badge?: number }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `relative flex min-w-0 flex-1 flex-col items-center gap-0.5 pb-2 pt-2.5 text-[11px] font-semibold ${isActive ? "text-brand-600 before:absolute before:inset-x-5 before:top-0 before:h-0.5 before:rounded-full before:bg-brand-600" : "text-gray-500"}`
      }
    >
      <span className="relative h-5 w-5">
        {icon}
        {badge ? (
          <span className="absolute -right-2 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-status-danger px-1 text-[10px] font-bold text-white">
            {badge > 9 ? "9+" : badge}
          </span>
        ) : null}
      </span>
      {label}
    </NavLink>
  );
}

export function VendorLayout() {
  usePwa();
  const { account, isLoading } = useVendorAuth();
  const location = useLocation();
  const { data } = useNotifications();

  if (isLoading) return <FullPageLoader />;
  if (!account) return <Navigate to="/vendor/login" replace state={{ from: location.pathname }} />;

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col bg-surface-subtle">
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-surface-border bg-surface px-4 pb-2.5 pt-[max(0.625rem,env(safe-area-inset-top))]">
        <BrandLogo height={28} />
        <NavLink to="/vendor/account" aria-label="Account" className="flex min-w-0 max-w-[60%] items-center gap-2.5">
          <span className="min-w-0 text-right text-xs">
            <span className="block truncate font-semibold text-gray-900">{niceName(account.full_name)}</span>
            <span className="text-gray-500">{account.kind === "vendor" ? "Vendor" : "Store POC"}</span>
          </span>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-bold text-white">
            {account.full_name.trim().slice(0, 1).toUpperCase()}
          </span>
        </NavLink>
      </header>

      <main className="flex-1 px-4 pb-24 pt-4">
        <Outlet />
      </main>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 mx-auto flex max-w-2xl border-t border-surface-border bg-surface pb-[env(safe-area-inset-bottom)]"
      >
        <Tab to="/vendor" end label="Home" icon={<IconGrid className="h-5 w-5" />} />
        <Tab to="/vendor/orders" label="Orders" icon={<IconBox className="h-5 w-5" />} />
        <Tab to="/vendor/tickets" label="Tickets" icon={<IconTicket className="h-5 w-5" />} />
        <Tab to="/vendor/documents" label="Documents" icon={<IconClipboard className="h-5 w-5" />} />
        <Tab to="/vendor/alerts" label="Alerts" icon={<IconActivity className="h-5 w-5" />} badge={data?.unread} />
      </nav>
    </div>
  );
}
