import { useEffect, useState, type ComponentType, type SVGProps } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { BrandLogo } from "@/components/ui/BrandLogo";
import {
  IconActivity,
  IconAlertTriangle,
  IconBox,
  IconCard,
  IconChart,
  IconClipboard,
  IconClock,
  IconClose,
  IconEdit,
  IconGrid,
  IconLogout,
  IconMapPin,
  IconMenu,
  IconReceipt,
  IconReport,
  IconSearch,
  IconShield,
  IconStore,
  IconUsers,
} from "@/components/ui/icons";

interface NavItem {
  label: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  permission?: string;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

// Nav items are declarative + permission-tagged, so the sidebar filters
// itself per spec section 8 ("navigation must dynamically change based
// on permissions") without any component knowing about roles. They are
// grouped by what people do with them; a group with nothing visible is hidden.
const NAV_GROUPS: NavGroup[] = [
  {
    title: "Overview",
    items: [{ label: "Dashboard", to: "/", icon: IconGrid }],
  },
  {
    title: "Orders",
    items: [
      { label: "Mark orders", to: "/orders", icon: IconClipboard, permission: "orders.mark" },
      { label: "Correct entries", to: "/orders/correct", icon: IconEdit, permission: "orders.correct" },
      { label: "Pending entries", to: "/pending", icon: IconAlertTriangle, permission: "orders.overview" },
      { label: "Daily overview", to: "/orders/overview", icon: IconChart, permission: "orders.overview" },
    ],
  },
  {
    title: "Stores & network",
    items: [
      { label: "Inventory", to: "/inventory", icon: IconBox, permission: "orders.view" },
      { label: "Stores", to: "/stores", icon: IconStore, permission: "stores.view" },
      { label: "Regions", to: "/regions", icon: IconMapPin, permission: "regions.view" },
      { label: "Monthwise virtual card", to: "/cards", icon: IconCard, permission: "orders.view" },
    ],
  },
  {
    title: "Compliance & accounts",
    items: [
      { label: "Compliance", to: "/compliance", icon: IconShield, permission: "compliance.upload" },
      { label: "Accounts", to: "/accounts", icon: IconReceipt, permission: "accounts.view" },
    ],
  },
  {
    title: "Reports",
    items: [{ label: "Reports", to: "/reports", icon: IconReport, permission: "orders.overview" }],
  },
  {
    title: "People",
    items: [
      { label: "Team & access", to: "/team", icon: IconUsers, permission: "employees.view" },
      // No permission: everyone can open it — admins see the whole team, everyone else sees their own record.
      { label: "Attendance", to: "/attendance", icon: IconClock },
      { label: "Activity", to: "/activity", icon: IconActivity, permission: "activity.view" },
    ],
  },
];

const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

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
      <BrandLogo tile height={30} />
      <div className="leading-tight">
        <div className="text-[15px] font-bold tracking-tight text-white">Veekay CRM</div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/40">Aquatech</div>
      </div>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, hasPermission, logout } = useAuth();
  const visibleGroups = NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((item) => !item.permission || hasPermission(item.permission)),
  })).filter((g) => g.items.length > 0);
  const primaryRole = user?.roles[0];

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-[4.5rem] shrink-0 items-center border-b border-white/5 px-5">
        <BrandMark />
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-4 pt-2" aria-label="Main">
        {visibleGroups.map((group) => (
          <div key={group.title} className="mt-4 first:mt-1">
            <p className="px-3 pb-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-white/30">{group.title}</p>
            <div className="space-y-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
                        : "text-white/60 hover:bg-white/5 hover:text-white"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute -left-3 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-aqua-300 to-brand-400" />
                      )}
                      <Icon
                        className={`h-[18px] w-[18px] shrink-0 ${
                          isActive ? "text-aqua-300" : "text-white/40 group-hover:text-white/70"
                        }`}
                      />
                      {item.label}
                    </>
                  )}
                </NavLink>
              );
            })}
            </div>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-white/5 p-3">
        <NavLink
          to="/account"
          onClick={onNavigate}
          title="My account"
          className="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-white/5"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-700 text-xs font-bold text-white ring-2 ring-white/10">
            {initials(user?.fullName ?? "")}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-white">{user?.fullName}</div>
            {primaryRole && (
              <div className="truncate text-xs text-white/50">{formatRoleLabel(primaryRole)}</div>
            )}
          </div>
        </NavLink>
        <button
          onClick={() => void logout()}
          className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white/60 transition-colors hover:bg-status-danger/20 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
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
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { hasPermission } = useAuth();
  const pages = NAV_ITEMS.filter((i) => !i.permission || hasPermission(i.permission));

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
      .sort((a, b) => b.to.length - a.to.length)[0]?.label ?? (location.pathname.startsWith("/account") ? "My account" : "Veekay CRM");

  return (
    <div className="min-h-screen bg-surface-subtle lg:pl-[17rem]">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[17rem] bg-ink-900 lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 animate-fade-in bg-ink-950/50"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[80vw] animate-slide-up bg-ink-900 shadow-lg">
            <button
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
              className="absolute right-3 top-5 rounded-md p-1.5 text-white/60 hover:bg-white/10 hover:text-white"
            >
              <IconClose className="h-5 w-5" />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      {/* Top bar */}
      <header className="sticky top-0 z-20 flex h-[4.5rem] items-center gap-3 border-b border-surface-border/70 bg-white/75 px-4 backdrop-blur-md sm:px-6 lg:px-10">
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
          className="-ml-1.5 rounded-md p-1.5 text-gray-600 hover:bg-surface-subtle hover:text-gray-900 lg:hidden"
        >
          <IconMenu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-gray-400">Veekay</span>
          <span className="text-gray-300">/</span>
          <h1 className="font-semibold text-ink-900">{currentTitle}</h1>
        </div>
        <button
          onClick={() => setPaletteOpen(true)}
          className="ml-auto flex items-center gap-2 rounded-lg border border-surface-border bg-white px-3 py-1.5 text-sm text-gray-400 shadow-sm transition-colors hover:border-gray-300 hover:text-gray-600"
        >
          <IconSearch className="h-4 w-4" />
          <span className="hidden sm:inline">Search…</span>
          <kbd className="hidden rounded border border-surface-border px-1.5 text-[10px] font-semibold sm:inline">Ctrl K</kbd>
        </button>
      </header>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        pages={pages.map((p) => ({ label: p.label, to: p.to }))}
        canSearchStores={hasPermission("stores.view")}
      />

      <main className="mx-auto w-full max-w-[1680px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
        <Outlet />
      </main>
    </div>
  );
}
