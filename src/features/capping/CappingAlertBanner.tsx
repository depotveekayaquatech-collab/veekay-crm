import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { IconAlertTriangle } from "@/components/ui/icons";
import { useAuth } from "@/features/auth/useAuth";
import { usePermission } from "@/hooks/usePermission";
import { getCappingAlerts, type UsageRow } from "@/services/capping";

const SHOWN = 6;
const n = (v: number) => v.toLocaleString("en-IN");

function Pill({ tone, children }: { tone: "danger" | "warning"; children: string }) {
  const cls = tone === "danger" ? "bg-status-danger/10 text-status-danger ring-status-danger/25" : "bg-status-warning/10 text-status-warning ring-status-warning/25";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ring-inset ${cls}`}>{children}</span>;
}

/** One store: how many bottles against its monthly limit, with a tick where today's pace is. */
function AlertRow({ r }: { r: UsageRow }) {
  const over = r.alert === "OVER";
  const limit = r.monthlyCap ?? 0;
  const used = limit > 0 ? Math.min(100, (r.used / limit) * 100) : 100;
  const pace = limit > 0 && r.allowedToDate !== null ? Math.min(100, (r.allowedToDate / limit) * 100) : null;
  const place = [r.city, r.state].filter(Boolean).join(", ");
  return (
    <li className="rounded-lg border border-surface-border bg-surface px-3 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-gray-900" title={r.outletName}>{r.outletName}</p>
          {place && <p className="truncate text-[11px] text-gray-500">{place}</p>}
        </div>
        <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-extrabold ${over ? "bg-status-danger/10 text-status-danger" : "bg-status-warning/10 text-status-warning"}`}>
          {over ? "Over limit" : "Ahead of pace"}
        </span>
      </div>
      <div className="relative mt-2 h-2 rounded-full bg-surface-border" role="progressbar" aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100} aria-label={`${r.outletName}: ${n(r.used)} of ${n(limit)} bottles`}>
        <div className={`h-full rounded-full ${over ? "bg-status-danger" : "bg-status-warning"}`} style={{ width: `${used}%` }} />
        {pace !== null && <span className="absolute -top-0.5 h-3 w-0.5 rounded bg-gray-900" style={{ left: `${pace}%` }} title={`On pace for today: ${n(r.allowedToDate ?? 0)}`} aria-hidden="true" />}
      </div>
      <div className="mt-1.5 flex flex-wrap items-baseline justify-between gap-x-3 text-xs text-gray-600">
        <span><b className="tabular-nums text-gray-900">{n(r.used)}</b> of {n(limit)} bottles this month</span>
        {over ? (
          <b className="tabular-nums text-status-danger">{n(r.excess)} over the limit</b>
        ) : (
          <span><b className="tabular-nums text-status-warning">{n(r.aheadBy ?? 0)} ahead</b> of today&apos;s {n(r.allowedToDate ?? 0)}</span>
        )}
      </div>
    </li>
  );
}

/** Warns an employee holding capping.alerts (and the Zepto partner login) when stores are over the monthly limit, or marking faster than the daily capping allows
 * for this point in the month. Renders nothing when there is nothing to manage (or no permission). */
export function CappingAlertBanner() {
  const { user, hasRole } = useAuth();
  const allowed = usePermission("capping.alerts") || (hasRole("partner") && user?.platformSlug?.toLowerCase() === "zepto");
  const { data } = useQuery({ queryKey: ["capping", "alerts"], queryFn: getCappingAlerts, enabled: allowed, staleTime: 60_000, retry: false });
  if (!allowed || !data || data.rows.length === 0) return null;

  const total = data.over + data.ahead;
  return (
    <section role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 shadow-card sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600">
            <IconAlertTriangle className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-extrabold text-gray-900 sm:text-base">Capping alert</h3>
            <p className="text-xs text-gray-500">{data.monthLabel} · day {data.day} of {data.daysInMonth} · bring the count down for these stores</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data.over > 0 && <Pill tone="danger">{`${data.over} over the limit`}</Pill>}
          {data.ahead > 0 && <Pill tone="warning">{`${data.ahead} ahead of pace`}</Pill>}
          <Link to="/capping" className="rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-xs font-bold text-brand-600 shadow-xs hover:text-brand-700">Open capping</Link>
        </div>
      </div>
      <ul className="mt-4 grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
        {data.rows.slice(0, SHOWN).map((r) => <AlertRow key={r.storeId} r={r} />)}
      </ul>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-gray-500">
        <span>The black tick on each bar is where today&apos;s pace is.{total > SHOWN ? ` Showing ${SHOWN} of ${total}.` : ""}</span>
        {total > SHOWN && <Link to="/capping" className="font-semibold text-brand-600 hover:text-brand-700">See all {total} in Capping</Link>}
      </div>
    </section>
  );
}
