import type { ReactNode, SVGProps } from "react";
import { useAdminDashboard } from "@/features/dashboard/useDashboardData";
import { DemoDataBanner } from "@/components/feedback/DemoDataBanner";
import { Skeleton } from "@/components/feedback/Skeleton";
import type { KpiKey, Tone, DashboardAlert, RegionStat, EmployeeStat, ActivityItem } from "@/types/dashboard";

// ---- tiny inline icons (no icon-library dependency) ----------------------
function IconBox(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M3 7l9-4 9 4-9 4-9-4Z" />
      <path d="M3 7v10l9 4 9-4V7" />
      <path d="M12 11v10" />
    </svg>
  );
}
function IconClock(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" />
    </svg>
  );
}
function IconCheck(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.5l2.5 2.5L16 9" />
    </svg>
  );
}
function IconTicket(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v1a2 2 0 0 0 0 4v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1a2 2 0 0 0 0-4V9Z" />
      <path d="M10 7v10" strokeDasharray="2 2" />
    </svg>
  );
}
function IconAlert(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M10.3 4.3 2.7 18a1.5 1.5 0 0 0 1.3 2.2h16a1.5 1.5 0 0 0 1.3-2.2L13.7 4.3a1.5 1.5 0 0 0-2.6 0Z" />
      <path d="M12 9.5v4" />
      <circle cx="12" cy="16.5" r="0.75" fill="currentColor" stroke="none" />
    </svg>
  );
}
function IconMap(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 21s7-6.1 7-11.3A7 7 0 0 0 5 9.7C5 14.9 12 21 12 21Z" />
      <circle cx="12" cy="9.5" r="2.3" />
    </svg>
  );
}
function IconUsers(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
      <circle cx="17.5" cy="9" r="2.2" />
      <path d="M15.5 14.2c2.4.5 4.5 2.7 4.5 5.8" />
    </svg>
  );
}
function IconPulse(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M3 12h4l2 7 4-14 2 7h6" />
    </svg>
  );
}
const ICONS_BY_KPI_KEY: Record<KpiKey, (props: SVGProps<SVGSVGElement>) => ReactNode> = {
  total_orders: IconBox,
  pending_orders: IconClock,
  completed_today: IconCheck,
  open_tickets: IconTicket,
};
// ---------------------------------------------------------------------------

const toneClasses: Record<Tone, { text: string; bg: string; dot: string; border: string; ring: string }> = {
  success: { text: "text-status-success", bg: "bg-status-success/10", dot: "bg-status-success", border: "border-status-success", ring: "ring-status-success/20" },
  warning: { text: "text-status-warning", bg: "bg-status-warning/10", dot: "bg-status-warning", border: "border-status-warning", ring: "ring-status-warning/20" },
  danger: { text: "text-status-danger", bg: "bg-status-danger/10", dot: "bg-status-danger", border: "border-status-danger", ring: "ring-status-danger/20" },
  info: { text: "text-status-info", bg: "bg-status-info/10", dot: "bg-status-info", border: "border-status-info", ring: "ring-status-info/20" },
  neutral: { text: "text-status-neutral", bg: "bg-status-neutral/10", dot: "bg-status-neutral", border: "border-status-neutral", ring: "ring-status-neutral/20" },
};

function completionTone(pct: number): Tone {
  if (pct >= 85) return "success";
  if (pct >= 70) return "warning";
  return "danger";
}

function KpiCard({ kpiKey, label, value, delta, tone }: { kpiKey: KpiKey; label: string; value: string; delta: string; tone: Tone }) {
  const t = toneClasses[tone];
  const Icon = ICONS_BY_KPI_KEY[kpiKey];
  return (
    <div className="overflow-hidden rounded-lg border border-surface-border bg-white shadow-sm transition-shadow hover:shadow-md">
      <div className={`h-1 w-full ${t.dot}`} />
      <div className="p-5">
        <div className="flex items-start justify-between">
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${t.bg} ${t.text}`}>
            <Icon className="h-5 w-5" />
          </span>
        </div>
        <p className={`mt-3 text-3xl font-semibold ${tone === "danger" || tone === "warning" ? t.text : "text-gray-900"}`}>{value}</p>
        <p className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${t.bg} ${t.text}`}>{delta}</p>
      </div>
    </div>
  );
}

function SectionCard({
  title,
  action,
  icon: Icon,
  tone = "neutral",
  children,
}: {
  title: string;
  action?: string;
  icon: (props: SVGProps<SVGSVGElement>) => ReactNode;
  tone?: Tone;
  children: ReactNode;
}) {
  const t = toneClasses[tone];
  return (
    <div className="rounded-lg border border-surface-border bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-surface-border px-5 py-4">
        <div className="flex items-center gap-2.5">
          <span className={`flex h-7 w-7 items-center justify-center rounded-md ${t.bg} ${t.text}`}>
            <Icon className="h-4 w-4" />
          </span>
          <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        </div>
        {action && <button className="text-sm font-medium text-brand-600 hover:text-brand-700">{action}</button>}
      </div>
      <div className="px-5 py-2">{children}</div>
    </div>
  );
}

function AlertRow({ alert }: { alert: DashboardAlert }) {
  const isHigh = alert.severity === "high";
  const tone = isHigh ? toneClasses.danger : toneClasses.warning;
  return (
    <div className={`my-2 flex items-start gap-3 rounded-md border-l-4 ${tone.border} ${tone.bg} px-3 py-3`}>
      <span className={`mt-0.5 rounded-full px-2 py-0.5 text-xs font-semibold ${isHigh ? "bg-status-danger text-white" : "bg-status-warning text-white"}`}>
        {isHigh ? "High" : "Medium"}
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-900">{alert.title}</p>
        <p className="text-xs text-gray-500">{alert.region}</p>
      </div>
    </div>
  );
}

function RegionRow({ region }: { region: RegionStat }) {
  const tone = toneClasses[completionTone(region.completionPct)];
  return (
    <div className="py-3">
      <div className="mb-1.5 flex items-center justify-between text-sm">
        <span className="font-medium text-gray-900">{region.name}</span>
        <span className={`font-semibold ${tone.text}`}>
          {region.completionPct}% <span className="font-normal text-gray-400">· {region.openIssues} open</span>
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-surface-subtle">
        <div className={`h-2 rounded-full ${tone.dot}`} style={{ width: `${region.completionPct}%` }} />
      </div>
    </div>
  );
}

function EmployeeRow({ employee }: { employee: EmployeeStat }) {
  const pct = Math.round((employee.completed / employee.assigned) * 100);
  const tone = toneClasses[completionTone(pct)];
  return (
    <tr className="border-t border-surface-border first:border-t-0">
      <td className="py-3 pr-4 text-sm font-medium text-gray-900">{employee.name}</td>
      <td className="py-3 pr-4 text-sm text-gray-500">{employee.region}</td>
      <td className="py-3 pr-4 text-sm text-gray-500">
        {employee.completed}/{employee.assigned}
      </td>
      <td className="py-3">
        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${tone.bg} ${tone.text}`}>{pct}%</span>
      </td>
    </tr>
  );
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const tone = toneClasses[item.tone];
  return (
    <div className="flex items-start gap-3 py-3">
      <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ring-4 ${tone.dot} ${tone.ring}`} />
      <div className="min-w-0">
        <p className="text-sm text-gray-900">{item.text}</p>
        <p className="text-xs text-gray-500">{item.time}</p>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Skeleton className="h-64 lg:col-span-2" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}

export function AdminDashboardPage() {
  const { data, isLoading } = useAdminDashboard();

  if (isLoading || !data) return <DashboardSkeleton />;

  const { data: dashboard, isDemo } = data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 sm:text-2xl">
            Here's what's happening across Veekay today
          </h2>
          <p className="mt-1 text-sm text-gray-500">Live overview of orders, tickets, and field teams.</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-status-success-soft px-3 py-1 text-xs font-medium text-status-success">
          <span className="h-1.5 w-1.5 rounded-full bg-status-success" />
          Live
        </span>
      </div>

      {isDemo && <DemoDataBanner />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {dashboard.kpis.map((kpi) => (
          <KpiCard key={kpi.key} kpiKey={kpi.key} label={kpi.label} value={kpi.value} delta={kpi.delta} tone={kpi.tone} />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SectionCard title="Needs your attention" action="View all" icon={IconAlert} tone="danger">
            <div className="flex flex-col divide-y-0">
              {dashboard.alerts.map((alert) => (
                <AlertRow key={alert.id} alert={alert} />
              ))}
            </div>
          </SectionCard>
        </div>

        <SectionCard title="Regional performance" icon={IconMap} tone="info">
          <div className="flex flex-col divide-y divide-surface-border">
            {dashboard.regions.map((region) => (
              <RegionRow key={region.name} region={region} />
            ))}
          </div>
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SectionCard title="Employee progress" action="View all" icon={IconUsers} tone="info">
            <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[420px]">
              <thead>
                <tr className="text-left text-xs font-medium uppercase tracking-wide text-gray-400">
                  <th className="pb-2 pr-4 font-medium">Employee</th>
                  <th className="pb-2 pr-4 font-medium">Region</th>
                  <th className="pb-2 pr-4 font-medium">Completed</th>
                  <th className="pb-2 font-medium">Progress</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.employees.map((employee) => (
                  <EmployeeRow key={employee.name} employee={employee} />
                ))}
              </tbody>
            </table>
            </div>
          </SectionCard>
        </div>

        <SectionCard title="Recent activity" icon={IconPulse} tone="success">
          <div className="flex flex-col divide-y divide-surface-border">
            {dashboard.activity.map((item) => (
              <ActivityRow key={item.time + item.text} item={item} />
            ))}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
