import { useMemo, useState, type ComponentType, type ReactNode, type SVGProps } from "react";
import { Link, Navigate } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import { getCalendar } from "@/services/orders";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { Select } from "@/components/ui/Select";
import { useTestReports } from "@/features/reports/testReports";
import { useDebounced } from "@/hooks/useDebounced";
import { listStores } from "@/services/stores";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useAuth } from "@/features/auth/useAuth";
import { usePermission } from "@/hooks/usePermission";
import { useEmployees } from "@/features/team/useTeam";
import { useInsights, useMyStores } from "@/features/orders/useOrders";
import { listActivity } from "@/services/activity";
import { BarList, DonutChart } from "@/features/dashboard/charts";
import { AlertStrip, DeepInsights, PerformanceKpis, TrendCard } from "@/features/dashboard/InsightsPanel";
import {
  IconActivity,
  IconChart,
  IconCheckCircle,
  IconClipboard,
  IconGrid,
  IconMapPin,
  IconStore,
  IconUsers,
} from "@/components/ui/icons";

/* ------------------------------------------------------------------ */
/* shared pieces                                                       */
/* ------------------------------------------------------------------ */

type Tone = "brand" | "success" | "warning" | "info";

const toneFill: Record<Tone, string> = {
  brand: "stat-brand",
  success: "stat-success",
  warning: "stat-warning",
  info: "stat-aqua",
};

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = "brand",
  loading,
}: {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  loading?: boolean;
}) {
  return (
    <div
      className={`${toneFill[tone]} relative overflow-hidden rounded-2xl p-5 text-white shadow-md transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-lg`}
    >
      <span aria-hidden="true" className="pointer-events-none absolute -right-8 -top-10 h-32 w-32 rounded-full bg-white/10" />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wider text-white/80">{label}</p>
          {loading ? (
            <Skeleton className="mt-2 h-8 w-16 !bg-white/25" />
          ) : (
            <p className="mt-1.5 text-[2rem] font-bold leading-none tabular-nums">{typeof value === "number" ? <AnimatedNumber value={value} /> : value}</p>
          )}
          {hint && !loading && <p className="mt-1.5 text-xs text-white/80">{hint}</p>}
        </div>
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/20 backdrop-blur-sm">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
      </div>
    </div>
  );
}

function ProgressBar({ percent }: { percent: number }) {
  const p = Math.max(0, Math.min(100, Math.round(percent)));
  const tone = p >= 85 ? "bg-status-success" : p >= 50 ? "bg-status-warning" : "bg-status-danger";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
      <div className={`h-full rounded-full transition-[width] ${tone}`} style={{ width: `${p}%` }} />
    </div>
  );
}

function Card({
  title,
  action,
  children,
  className = "",
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-surface-border bg-surface shadow-card ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-surface-border/80 px-5 py-4">
        <h3 className="text-sm font-bold text-gray-900">{title}</h3>
        {action}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

function CardLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="text-xs font-medium text-brand-600 hover:text-brand-700">
      {children}
    </Link>
  );
}

function ago(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? `${hrs}h ago` : new Date(iso).toLocaleDateString();
}

function trendDelta(today: number, yesterday: number): { text: string; tone: Tone } {
  if (yesterday === 0) return { text: today > 0 ? "new today" : "no change", tone: "info" };
  const pct = Math.round(((today - yesterday) / yesterday) * 100);
  if (pct === 0) return { text: "same as yesterday", tone: "info" };
  return { text: `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}% vs yesterday`, tone: pct > 0 ? "success" : "warning" };
}

/* ------------------------------------------------------------------ */
/* admin dashboard                                                     */
/* ------------------------------------------------------------------ */

const ALL_PLATFORMS = "__all";
const STORE_PAGE = 15;

const STATUS_COLORS: Record<string, string> = {
  LIVE: "#0f7b57",
  PENDING: "#d99a2b",
  CLOSE: "#98a0b5",
};

function AdminDashboard() {
  const { data: insights, isLoading } = useInsights();
  const { data: employees } = useEmployees(1, "");
  const { data: activity, isLoading: activityLoading } = useQuery({
    queryKey: ["dashboard-activity"],
    queryFn: () => listActivity({ page: 1, pageSize: 8 }),
  });

  const totalStores = insights
    ? insights.storeStatus.LIVE + insights.storeStatus.PENDING + insights.storeStatus.CLOSE
    : 0;
  const overallPercent =
    insights && insights.platforms.length
      ? insights.platforms.reduce((s, p) => s + p.entriesDone, 0) /
        Math.max(1, insights.platforms.reduce((s, p) => s + p.totalStores, 0)) *
        100
      : 0;
  // One donut per platform: the server sends the counts, not every store.
  const statusByPlatform = useMemo(
    () => (insights?.statusByPlatform ?? []).map((p) => ({ label: p.label, total: p.total, counts: { LIVE: p.live, PENDING: p.pending, CLOSE: p.close } })),
    [insights],
  );
  const [statusPick, setStatusPick] = useState<string | null>(null);
  const statusChoice = statusPick ?? statusByPlatform[0]?.label ?? ALL_PLATFORMS;
  const statusShown = useMemo(() => {
    if (statusChoice === ALL_PLATFORMS) {
      const counts = { LIVE: 0, PENDING: 0, CLOSE: 0 };
      statusByPlatform.forEach((p) => {
        counts.LIVE += p.counts.LIVE;
        counts.PENDING += p.counts.PENDING;
        counts.CLOSE += p.counts.CLOSE;
      });
      return { label: "All platforms", total: statusByPlatform.reduce((n, p) => n + p.total, 0), counts };
    }
    return statusByPlatform.find((p) => p.label === statusChoice) ?? null;
  }, [statusByPlatform, statusChoice]);
  const testReports = useTestReports("zepto");
  const delta = insights ? trendDelta(insights.bottlesToday, insights.bottlesYesterday) : null;

  // The store directory is searched and paged on the server (15 rows per request), never downloaded whole.
  const [storePartner, setStorePartner] = useState("");
  const [storeQuery, setStoreQuery] = useState("");
  const [storePage, setStorePage] = useState(1);
  const storeSearch = useDebounced(storeQuery.trim(), 300);
  const directory = useQuery({
    queryKey: ["dashboard-stores", storePartner, storeSearch, storePage],
    queryFn: () => listStores({ page: storePage, pageSize: STORE_PAGE, partner: storePartner || undefined, search: storeSearch || undefined }),
    placeholderData: (prev) => prev,
  });
  const storeRows = directory.data?.items ?? [];
  const storeTotal = directory.data?.total ?? 0;
  const storePages = Math.max(1, Math.ceil(storeTotal / STORE_PAGE));

  const quickActions = [
    { to: "/orders/overview", label: "Daily overview", icon: IconChart, perm: "orders.overview" },
    { to: "/orders/correct", label: "Correct entries", icon: IconGrid, perm: "orders.correct" },
    { to: "/team", label: "Team & access", icon: IconUsers, perm: "employees.view" },
    { to: "/stores", label: "Manage stores", icon: IconStore, perm: "stores.view" },
    { to: "/activity", label: "Activity log", icon: IconActivity, perm: "activity.view" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <AlertStrip insights={insights} />

      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={IconClipboard}
          label="Bottles today"
          value={insights?.bottlesToday ?? 0}
          hint={delta?.text}
          tone="brand"
          loading={isLoading}
        />
        <StatCard
          icon={IconCheckCircle}
          label="Entries today"
          value={insights?.entriesToday ?? 0}
          hint={`${Math.round(overallPercent)}% of stores marked`}
          tone="success"
          loading={isLoading}
        />
        <StatCard
          icon={IconStore}
          label="Live stores"
          value={insights?.storeStatus.LIVE ?? 0}
          hint={`${totalStores} total · ${insights?.storeStatus.PENDING ?? 0} pending`}
          tone="info"
          loading={isLoading}
        />
        <StatCard
          icon={IconUsers}
          label="Employees"
          value={employees?.total ?? 0}
          hint={insights ? `${insights.platforms.length} platforms` : undefined}
          tone="warning"
          loading={isLoading}
        />
      </div>

      <PerformanceKpis insights={insights} />

      {/* Trend + status */}
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <TrendCard insights={insights} />

        <Card
          title="Store status"
          action={
            statusByPlatform.length > 0 ? (
              <div className="w-40 [&_label]:sr-only">
                <Select
                  label="Platform"
                  value={statusChoice}
                  onChange={(e) => setStatusPick(e.target.value)}
                  options={[...statusByPlatform.map((p) => ({ value: p.label, label: p.label })), { value: ALL_PLATFORMS, label: "All platforms" }]}
                />
              </div>
            ) : undefined
          }
        >
          {isLoading || !insights ? (
            <Skeleton className="h-40" />
          ) : (
            <div className="flex flex-col gap-6">
              {statusShown ? (
                <DonutChart
                  centerValue={statusShown.total}
                  centerLabel={statusChoice === ALL_PLATFORMS ? "stores in total" : "stores"}
                  slices={(["LIVE", "PENDING", "CLOSE"] as const).map((k) => ({
                    label: k[0] + k.slice(1).toLowerCase(),
                    value: statusShown.counts[k],
                    color: STATUS_COLORS[k],
                  }))}
                />
              ) : (
                <p className="text-sm text-gray-500">No stores yet.</p>
              )}

              {/* Second section: test reports (Zepto only for now) */}
              <section className="-mx-5 -mb-5 border-t border-surface-border bg-surface-subtle/60 px-5 py-5" aria-label="Test reports">
                <div className="flex items-center justify-between gap-3">
                  <h4 className="text-sm font-bold text-heading">Test reports</h4>
                  <CardLink to="/reports?tab=test">Manage →</CardLink>
                </div>
                {testReports.isLoading ? (
                  <Skeleton className="mt-3 h-16" />
                ) : testReports.data?.platform.enabled ? (
                  <>
                    <div className="mt-3 flex items-end gap-3">
                      <p className="text-3xl font-extrabold tabular-nums leading-none text-heading">{testReports.data.summary.reportsTotal}</p>
                      <p className="pb-0.5 text-xs text-gray-500">
                        {testReports.data.platform.name} test report{testReports.data.summary.reportsTotal === 1 ? "" : "s"} available
                        <br />
                        across {testReports.data.summary.reportsTotal} of {testReports.data.summary.statesTotal} states
                      </p>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      <Badge tone="success">{testReports.data.summary.valid} valid</Badge>
                      {testReports.data.summary.expiring > 0 && <Badge tone="warning">{testReports.data.summary.expiring} expiring soon</Badge>}
                      {testReports.data.summary.expired > 0 && <Badge tone="danger">{testReports.data.summary.expired} expired</Badge>}
                      {testReports.data.summary.missing > 0 && <Badge tone="neutral">{testReports.data.summary.missing} states with none</Badge>}
                    </div>
                  </>
                ) : (
                  <p className="mt-3 text-sm text-gray-500">Test reports aren't available yet.</p>
                )}
              </section>
            </div>
          )}
        </Card>
      </div>

      {/* Platform progress + leaderboard */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Today's completion by platform">
          {isLoading || !insights ? (
            <Skeleton className="h-40" />
          ) : insights.platforms.length === 0 ? (
            <p className="text-sm text-gray-500">No platforms configured.</p>
          ) : (
            <div className="flex flex-col gap-4">
              {insights.platforms.map((p) => (
                <div key={p.slug}>
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-gray-900">{p.label}</p>
                    <Badge tone={p.percent >= 85 ? "success" : p.percent >= 50 ? "warning" : "danger"}>
                      {Math.round(p.percent)}%
                    </Badge>
                  </div>
                  <div className="mt-2">
                    <ProgressBar percent={p.percent} />
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                    <span>{p.entriesDone} / {p.totalStores} stores</span>
                    <span>{p.bottles} bottles</span>
                    <span>{p.employees} employees</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Top performers today" action={<CardLink to="/orders/overview">All →</CardLink>}>
          {isLoading || !insights ? (
            <Skeleton className="h-40" />
          ) : insights.leaderboard.length === 0 ? (
            <p className="text-sm text-gray-500">No entries yet today.</p>
          ) : (
            <BarList
              items={insights.leaderboard.map((l) => ({
                label: l.employeeName,
                sub: `${l.entriesDone}/${l.totalStores} stores${l.regionName ? ` · ${l.regionName}` : ""}`,
                value: l.bottles,
                max: Math.max(...insights.leaderboard.map((x) => x.bottles), 1),
                suffix: " btl",
              }))}
            />
          )}
        </Card>
      </div>

      <DeepInsights insights={insights} />

      {/* Store coverage + attention — same `stores` data as the Stores page / Sheet sync */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Store coverage by region"
          action={
            insights?.lastStoreSync ? (
              <span className="text-xs text-gray-400">Synced {ago(insights.lastStoreSync)}</span>
            ) : (
              <CardLink to="/stores">Manage →</CardLink>
            )
          }
        >
          {isLoading || !insights ? (
            <Skeleton className="h-40" />
          ) : insights.storesByRegion.length === 0 ? (
            <p className="text-sm text-gray-500">No stores yet.</p>
          ) : (
            <div className="flex flex-col gap-3.5">
              {insights.storesByRegion.map((r) => {
                const max = Math.max(...insights.storesByRegion.map((x) => x.total), 1);
                return (
                  <div key={r.label}>
                    <div className="mb-1 flex items-baseline justify-between text-sm">
                      <span className="font-medium text-gray-800">{r.label}</span>
                      <span className="tabular-nums text-gray-500">
                        {r.live} live<span className="text-gray-300"> / {r.total}</span>
                      </span>
                    </div>
                    <div className="flex h-2 w-full overflow-hidden rounded-full bg-surface-muted">
                      <div className="h-full bg-status-success" style={{ width: `${(r.live / max) * 100}%` }} />
                      <div
                        className="h-full bg-status-warning/50"
                        style={{ width: `${((r.total - r.live) / max) * 100}%` }}
                      />
                    </div>
                  </div>
                );
              })}
              {insights.storesByState.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1.5 border-t border-surface-border pt-3">
                  {insights.storesByState.map((s) => (
                    <span
                      key={s.label}
                      className="rounded-full bg-surface-subtle px-2 py-0.5 text-xs text-gray-600"
                    >
                      {s.label} <span className="font-medium text-gray-900">{s.total}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>

        <Card
          title="Stores needing attention"
          action={<CardLink to="/stores">All stores →</CardLink>}
        >
          {isLoading || !insights ? (
            <Skeleton className="h-40" />
          ) : insights.attentionStores.length === 0 ? (
            <p className="text-sm text-gray-500">Every store is live. 🎉</p>
          ) : (
            <ul className="flex max-h-72 flex-col divide-y divide-surface-border overflow-auto">
              {insights.attentionStores.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-gray-900">{s.name}</p>
                    <p className="text-xs text-gray-500">
                      {s.externalCode}
                      {s.platform ? ` · ${s.platform}` : ""}
                      {s.city ? ` · ${s.city}` : s.state ? ` · ${s.state}` : ""}
                    </p>
                  </div>
                  <Badge tone={s.status === "PENDING" ? "warning" : "neutral"}>{s.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Store directory — searched and paged on the server */}
      <Card
        title="All stores"
        action={
          <div className="flex items-center gap-2">
            <span className="hidden text-xs text-gray-400 sm:inline">{storeTotal.toLocaleString()} match</span>
            <CardLink to="/stores">Open Stores →</CardLink>
          </div>
        }
      >
        {isLoading || !insights ? (
          <Skeleton className="h-56" />
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex flex-wrap gap-1.5">
                {[{ slug: "", label: "All", count: insights.statusByPlatform.reduce((n, p) => n + p.total, 0) }, ...insights.statusByPlatform.map((p) => ({ slug: p.slug, label: p.label, count: p.total }))].map((p) => (
                  <button
                    key={p.slug || "all"}
                    onClick={() => {
                      setStorePartner(p.slug);
                      setStorePage(1);
                    }}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                      storePartner === p.slug
                        ? "bg-brand-500 text-white"
                        : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
                    }`}
                  >
                    {p.label} ({p.count.toLocaleString()})
                  </button>
                ))}
              </div>
              <input
                value={storeQuery}
                onChange={(e) => {
                  setStoreQuery(e.target.value);
                  setStorePage(1);
                }}
                aria-label="Search stores"
                placeholder="Search name, code, city…"
                className="ml-auto h-9 w-full rounded-md border border-surface-border px-3 text-sm outline-none focus:border-brand-400 sm:w-64"
              />
            </div>

            <div className={`stacked-table overflow-auto rounded-lg border border-surface-border transition-opacity ${directory.isFetching ? "opacity-70" : ""}`}>
              <table className="w-full min-w-[640px] text-sm">
                <thead className="bg-surface-subtle">
                  <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-4 py-2.5">Store</th>
                    <th className="px-4 py-2.5">Code</th>
                    <th className="px-4 py-2.5">Platform</th>
                    <th className="px-4 py-2.5">Region / State</th>
                    <th className="px-4 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {directory.isLoading && (
                    <tr>
                      <td colSpan={5} className="px-4 py-10 text-center text-gray-400">Loading…</td>
                    </tr>
                  )}
                  {!directory.isLoading && storeRows.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-10 text-center text-gray-500">No stores match.</td>
                    </tr>
                  )}
                  {storeRows.map((s) => (
                    <tr key={s.id} className="border-t border-surface-border">
                      <td className="px-4 py-2.5 font-medium text-gray-900" data-label="Store">{s.name}</td>
                      <td className="px-4 py-2.5 text-gray-500" data-label="Code">{s.externalCode}</td>
                      <td className="px-4 py-2.5" data-label="Platform">{s.partnerName ?? "—"}</td>
                      <td className="px-4 py-2.5 text-gray-500" data-label="Region / State">
                        {s.regionName ?? s.state ?? "—"}
                        {s.city ? ` · ${s.city}` : ""}
                      </td>
                      <td className="px-4 py-2.5" data-label="Status">
                        <Badge tone={s.status === "LIVE" ? "success" : s.status === "PENDING" ? "warning" : "neutral"}>{s.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {storePages > 1 && (
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-gray-500">Page {storePage} of {storePages.toLocaleString()}</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={storePage <= 1}
                    onClick={() => setStorePage((p) => Math.max(1, p - 1))}
                    className="rounded-lg border border-surface-border bg-surface px-3 py-1.5 font-semibold text-gray-700 hover:bg-surface-subtle disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={storePage >= storePages}
                    onClick={() => setStorePage((p) => Math.min(storePages, p + 1))}
                    className="rounded-lg border border-surface-border bg-surface px-3 py-1.5 font-semibold text-gray-700 hover:bg-surface-subtle disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Activity + quick actions */}
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <Card title="Recent activity" action={<CardLink to="/activity">View all →</CardLink>}>
          {activityLoading && <Skeleton className="h-40" />}
          {activity && activity.items.length === 0 && (
            <p className="text-sm text-gray-500">Nothing has happened yet.</p>
          )}
          {activity && activity.items.length > 0 && (
            <ul className="flex flex-col divide-y divide-surface-border">
              {activity.items.map((a) => (
                <li key={a.id} className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-gray-900">
                      {(a.action.split(".")[1] ?? a.action).replace(/_/g, " ")}
                      <span className="text-gray-400"> · {a.entityType.replace(/_/g, " ")}</span>
                    </p>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {a.actorName ?? "System"} · {ago(a.createdAt)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Quick actions">
          <div className="grid gap-3 sm:grid-cols-2">
            {quickActions.map((qa) => (
              <QuickAction key={qa.to} {...qa} />
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function QuickAction({
  to,
  label,
  icon: Icon,
  perm,
}: {
  to: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  perm: string;
}) {
  const allowed = usePermission(perm);
  if (!allowed) return null;
  return (
    <Link
      to={to}
      className="flex items-center gap-3 rounded-lg border border-surface-border px-4 py-3 text-sm font-medium text-gray-700 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
    >
      <Icon className="h-[18px] w-[18px] text-gray-400" />
      {label}
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/* employee dashboard                                                  */
/* ------------------------------------------------------------------ */

function EmployeeDashboard() {
  const { user } = useAuth();
  const { data: stores = [], isLoading } = useMyStores();

  const calendars = useQueries({
    queries: stores.map((s) => ({
      queryKey: ["calendar", s.id, undefined, undefined],
      queryFn: () => getCalendar(s.id),
    })),
  });

  const rows = stores.map((s, i) => {
    const today = calendars[i]?.data?.days.find((d) => d.isToday);
    return { store: s, marked: Boolean(today?.marked), count: today?.count ?? 0, loading: calendars[i]?.isLoading };
  });
  const markedToday = rows.filter((r) => r.marked).length;
  const bottlesToday = rows.reduce((sum, r) => sum + (r.marked ? r.count : 0), 0);
  const pct = stores.length ? Math.round((markedToday / stores.length) * 100) : 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={IconStore} label="My stores" value={stores.length} tone="brand" loading={isLoading} />
        <StatCard icon={IconClipboard} label="Bottles today" value={bottlesToday} tone="success" loading={isLoading} />
        <StatCard
          icon={IconChart}
          label="Platform"
          value={<span className="text-lg">{user?.platformLabel ?? "—"}</span>}
          tone="info"
        />
        <StatCard
          icon={IconMapPin}
          label="Scope"
          value={<span className="text-lg">{user?.regionName ?? "State-based"}</span>}
          tone="warning"
        />
      </div>

      <Card title="Today's progress">
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-600">{markedToday} of {stores.length} stores marked</span>
          <span className="font-semibold text-gray-900">{pct}%</span>
        </div>
        <div className="mt-2">
          <ProgressBar percent={pct} />
        </div>
      </Card>

      <Card title="Today's stores" action={<CardLink to="/orders">Go to calendar →</CardLink>}>
        {isLoading && <Skeleton className="h-40" />}
        {!isLoading && stores.length === 0 && (
          <EmptyState title="No stores assigned yet" description="Ask your admin to set your region or states." />
        )}
        {stores.length > 0 && (
          <ul className="flex flex-col divide-y divide-surface-border">
            {rows.map((r) => (
              <li key={r.store.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-gray-900">{r.store.name}</p>
                  <p className="text-xs text-gray-500">
                    {r.store.externalCode}
                    {r.store.city ? ` · ${r.store.city}` : ""}
                  </p>
                </div>
                {r.loading ? (
                  <Skeleton className="h-5 w-16" />
                ) : r.marked ? (
                  <Badge tone="success">{r.count} bottles</Badge>
                ) : (
                  <Badge tone="warning">Not marked</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Link
        to="/orders"
        className="flex items-center justify-center gap-2 rounded-xl bg-brand-500 px-5 py-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-600"
      >
        <IconCheckCircle className="h-5 w-5" />
        Mark today's orders
      </Link>
    </div>
  );
}

/* ------------------------------------------------------------------ */

export function DashboardPage() {
  const { user } = useAuth();
  const isAdmin = usePermission("orders.overview");
  const canOrders = usePermission("orders.view");
  const isAccountant = usePermission("accounts.view");
  const firstName = user?.fullName?.split(" ")[0] ?? "there";
  const dateLabel = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  if (isAccountant && !canOrders && !isAdmin) return <Navigate to="/accounts" replace />;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={`Welcome back, ${firstName}`} subtitle={dateLabel} />
      {isAdmin ? <AdminDashboard /> : <EmployeeDashboard />}
    </div>
  );
}
