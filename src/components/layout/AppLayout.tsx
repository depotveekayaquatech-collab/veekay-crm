import { useEffect, useState, type ComponentType, type SVGProps } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import {
  IconActivity,
  IconChart,
  IconClipboard,
  IconClose,
  IconGrid,
  IconLogout,
  IconMapPin,
  IconMenu,
  IconStore,
  IconUsers,
} from "@/components/ui/icons";

interface NavItem {
  label: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  permission?: string;
}

// Nav items are declarative + permission-tagged, so the sidebar filters
// itself per spec section 8 ("navigation must dynamically change based
// on permissions") without any component knowing about roles.
const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", to: "/", icon: IconGrid },
  { label: "Mark orders", to: "/orders", icon: IconClipboard, permission: "orders.mark" },
  { label: "Daily overview", to: "/orders/overview", icon: IconChart, permission: "orders.overview" },
  { label: "Correct entries", to: "/orders/correct", icon: IconGrid, permission: "orders.correct" },
  { label: "Team & access", to: "/team", icon: IconUsers, permission: "employees.view" },
  { label: "Stores", to: "/stores", icon: IconStore, permission: "stores.view" },
  { label: "Regions", to: "/regions", icon: IconMapPin, permission: "regions.view" },
  { label: "Activity", to: "/activity", icon: IconActivity, permission: "activity.view" },
];

function formatRoleLabel(role: string): string {
  return role
    .split("_")
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

function BrandMark() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white shadow-sm">
        V
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-gray-900">Veekay CRM</span>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, hasPermission, logout } = useAuth();
  const visibleItems = NAV_ITEMS.filter((item) => !item.permission || hasPermission(item.permission));
  const primaryRole = user?.roles[0];

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 shrink-0 items-center px-5">
        <BrandMark />
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end
              onClick={onNavigate}
              className={({ isActive }) =>
                `group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-600 hover:bg-surface-subtle hover:text-gray-900"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    className={`h-[18px] w-[18px] shrink-0 ${
                      isActive ? "text-brand-600" : "text-gray-400 group-hover:text-gray-600"
                    }`}
                  />
                  {item.label}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="shrink-0 border-t border-surface-border p-3">
        <div className="flex items-center gap-3 rounded-md px-2 py-2">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
            {initials(user?.fullName ?? "")}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-gray-900">{user?.fullName}</div>
            {primaryRole && (
              <div className="truncate text-xs text-gray-500">{formatRoleLabel(primaryRole)}</div>
            )}
          </div>
        </div>
        <button
          onClick={() => void logout()}
          className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-status-danger-soft hover:text-status-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <IconLogout className="h-[18px] w-[18px]" />
          Sign out
        </button>
      </div>
    </div>
  );
}

export function AppLayout() {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Lock body scroll while the mobile drawer is open.
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  const currentTitle =
    [...NAV_ITEMS]
      .filter((item) => location.pathname.startsWith(item.to))
      .sort((a, b) => b.to.length - a.to.length)[0]?.label ?? "Veekay CRM";

  return (
    <div className="min-h-screen bg-surface-subtle lg:pl-[17rem]">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[17rem] border-r border-surface-border bg-white lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 animate-fade-in bg-gray-900/40"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[80vw] animate-slide-up border-r border-surface-border bg-white shadow-lg">
            <button
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
              className="absolute right-3 top-4 rounded-md p-1.5 text-gray-500 hover:bg-surface-subtle hover:text-gray-900"
            >
              <IconClose className="h-5 w-5" />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      {/* Top bar */}
      <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-surface-border bg-white/85 px-4 backdrop-blur-md sm:px-6 lg:px-10">
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
          className="-ml-1.5 rounded-md p-1.5 text-gray-600 hover:bg-surface-subtle hover:text-gray-900 lg:hidden"
        >
          <IconMenu className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-semibold text-gray-900">{currentTitle}</h1>
      </header>

      <main className="mx-auto w-full max-w-[1680px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
        <Outlet />
      </main>
    </div>
  );
}
