import { Suspense, useEffect, useState, type ComponentType, type SVGProps } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { ShortcutsModal, type GoShortcut } from "@/components/layout/ShortcutsModal";
import { BrandLogo } from "@/components/ui/BrandLogo";
import {
  IconActivity,
  IconBox,
  IconCard,
  IconClipboard,
  IconClock,
  IconClose,
  IconGrid,
  IconLogout,
  IconMenu,
  IconReceipt,
  IconRefresh,
  IconWallet,
  IconReport,
  IconSearch,
  IconShield,
  IconStore,
  IconTicket,
  IconUsers,
} from "@/components/ui/icons";

interface NavItem {
  label: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  permission?: string;
  /** Visible if the user holds any of these (used by hub pages with several tabs). */
  anyPermission?: string[];
  /** Highlight for nested routes too (e.g. /orders/pending under Orders). */
  prefix?: boolean;
  /** Hidden for accounts holding this role (partner logins don't use the dashboard or attendance). */
  excludeRole?: string | string[];
  /** Shown only to accounts holding this role (e.g. the partner delivery-report download). */
  requireRole?: string;
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
    items: [{ label: "Dashboard", to: "/", icon: IconGrid, excludeRole: "developer" }],
  },
  {
    title: "Operations",
    items: [
      {
        label: "Orders",
        to: "/orders",
        icon: IconClipboard,
        anyPermission: ["orders.view", "orders.mark", "orders.overview", "orders.correct"],
        prefix: true,
      },
      { label: "Tickets", to: "/tickets", icon: IconTicket, anyPermission: ["tickets.view", "tickets.manage"] },
    ],
  },
  {
    title: "Stores & vendors",
    items: [
      { label: "Stores", to: "/stores", icon: IconStore, permission: "stores.view" },
      { label: "Vendors", to: "/inventory", icon: IconBox, permission: "orders.view" },
      { label: "Store cards", to: "/cards", icon: IconCard, permission: "orders.view" },
    ],
  },
  {
    title: "Compliance & billing",
    items: [
      { label: "Compliance", to: "/compliance", icon: IconShield, permission: "compliance.upload" },
      { label: "Billing", to: "/accounts", icon: IconReceipt, permission: "accounts.view" },
      { label: "Cash purchases", to: "/cash", icon: IconWallet, anyPermission: ["cash.view", "cash.add"], excludeRole: "partner" },
    ],
  },
  {
    title: "Insights",
    items: [
      { label: "Reports", to: "/reports", icon: IconReport, permission: "orders.overview" },
      { label: "Delivery reports", to: "/delivery-reports", icon: IconReport, permission: "reports.delivery", requireRole: "partner" },
      { label: "Audit log", to: "/activity", icon: IconActivity, permission: "activity.view" },
    ],
  },
  {
    title: "Developer",
    items: [
      { label: "Data sync", to: "/data-sync", icon: IconRefresh, permission: "sheets.sync" },
      { label: "Cash purchase", to: "/developer/cash", icon: IconWallet, permission: "cash.adjust" },
    ],
  },
  {
    title: "People & access",
    items: [
      // No permission: every staff member can open it — admins see the whole team, everyone else sees their own record.
      { label: "Attendance", to: "/attendance", icon: IconClock, excludeRole: ["partner", "developer"] },
      { label: "Users & access", to: "/team", icon: IconUsers, permission: "employees.view" },
    ],
  },
];

const canSee = (item: NavItem, has: (p: string) => boolean, allRoles: string[]) => {
  // A developer who is also an admin (the demo login) is an admin first: the developer-only trimming doesn't apply.
  const roles = allRoles.includes("admin") ? allRoles.filter((r) => r !== "developer") : allRoles;
  return (
    !(item.excludeRole && [item.excludeRole].flat().some((r) => roles.includes(r))) &&
    !(item.requireRole && !roles.includes(item.requireRole)) &&
    (item.anyPermission ? item.anyPermission.some(has) : !item.permission || has(item.permission))
  );
};

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
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/40">Aquatrack</div>
      </div>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, hasPermission, logout } = useAuth();
  const visibleGroups = NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((item) => canSee(item, hasPermission, user?.roles ?? [])),
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
            <p className="px-3 pb-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-brand-300/70">{group.title}</p>
            <div className="space-y-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={!item.prefix}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-gradient-to-r from-brand-500/30 to-brand-500/5 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
                        : "text-white/60 hover:bg-white/5 hover:text-white"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute -left-3 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-aqua-300 to-brand-400 shadow-[0_0_10px_rgb(var(--brand-400)/0.8)]" />
                      )}
                      <Icon
                        aria-hidden="true"
                        className={`h-[18px] w-[18px] shrink-0 ${
                          isActive ? "text-brand-300" : "text-white/40 group-hover:text-white/70"
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

function PageFallback() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading page">
      <div className="h-8 w-56 animate-pulse rounded-lg bg-surface-border/60" />
      <div className="h-40 animate-pulse rounded-2xl bg-surface-border/50" />
      <div className="h-64 animate-pulse rounded-2xl bg-surface-border/40" />
    </div>
  );
}

export function AppLayout() {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const pages = NAV_ITEMS.filter((i) => canSee(i, hasPermission, user?.roles ?? []));

  // "g then o" style jumps, limited to pages this user can open.
  const goKeys: (GoShortcut & { to: string })[] = [
    { key: "d", label: "Dashboard", to: "/" },
    { key: "o", label: "Orders", to: "/orders" },
    { key: "t", label: "Tickets", to: "/tickets" },
    { key: "s", label: "Stores", to: "/stores" },
    { key: "r", label: "Reports", to: "/reports" },
    { key: "a", label: "Attendance", to: "/attendance" },
  ].filter((g) => pages.some((p) => p.to === g.to));

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

  // Single-key shortcuts: "?" opens help, "g" then a letter jumps to a page. Never fires while typing.
  useEffect(() => {
    let armedAt = 0;
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
      if (e.key === "?") {
        e.preventDefault();
        setHelpOpen(true);
        return;
      }
      const key = e.key.toLowerCase();
      if (key === "g") {
        armedAt = Date.now();
        return;
      }
      if (armedAt && Date.now() - armedAt < 1200) {
        const hit = goKeys.find((g) => g.key === key);
        armedAt = 0;
        if (hit) navigate(hit.to);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

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
      <a
        href="#main-content"
        className="sr-only z-50 rounded-lg bg-surface px-4 py-2 text-sm font-semibold text-heading shadow-lg focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to main content
      </a>
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
      <header className="sticky top-0 z-20 flex h-[4.5rem] items-center gap-3 border-b border-surface-border/70 bg-surface/75 px-4 backdrop-blur-md sm:px-6 lg:px-10">
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
          <h1 className="font-semibold text-heading">{currentTitle}</h1>
        </div>
        <button
          onClick={() => setPaletteOpen(true)}
          aria-label="Search pages and stores"
          className="ml-auto flex items-center gap-2 rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm text-gray-500 shadow-sm transition-colors hover:border-gray-300 hover:text-gray-700"
        >
          <IconSearch className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">Search…</span>
          <kbd className="hidden rounded border border-surface-border px-1.5 text-[10px] font-semibold sm:inline">Ctrl K</kbd>
        </button>
        <button
          onClick={() => setHelpOpen(true)}
          aria-label="Keyboard shortcuts"
          title="Keyboard shortcuts (?)"
          className="hidden h-9 w-9 items-center justify-center rounded-lg border border-surface-border bg-surface text-sm font-bold text-gray-500 shadow-sm transition-colors hover:border-gray-300 hover:text-gray-800 sm:flex"
        >
          ?
        </button>
      </header>

      <ShortcutsModal open={helpOpen} onClose={() => setHelpOpen(false)} go={goKeys} />

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        pages={pages.map((p) => ({ label: p.label, to: p.to }))}
        canSearchStores={hasPermission("stores.view")}
      />

      <main id="main-content" tabIndex={-1} className="mx-auto scroll-mt-24 outline-none w-full max-w-[1680px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
        <Suspense fallback={<PageFallback />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
