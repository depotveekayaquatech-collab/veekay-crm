import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { IconAlertTriangle } from "@/components/ui/icons";
import { usePermission } from "@/hooks/usePermission";
import { getCappingAlerts, type CapRow } from "@/services/capping";

const SHOWN = 5;
const n = (v: number) => v.toLocaleString("en-IN");

function line(r: CapRow): string {
  if (r.alert === "OVER") return `${n(r.used)} marked, cap ${n(r.monthlyCap ?? 0)} (${n(r.excess)} over)`;
  return `${n(r.used)} marked, ${n(r.allowedToDate ?? 0)} allowed by today (${n(r.aheadBy ?? 0)} ahead), cap ${n(r.monthlyCap ?? 0)}`;
}

/** Warns an employee holding capping.alerts when their stores are over the monthly cap, or marking faster than the cap
 * allows for this point in the month. Renders nothing when there is nothing to manage (or no permission). */
export function CappingAlertBanner() {
  const allowed = usePermission("capping.alerts");
  const { data } = useQuery({
    queryKey: ["capping", "alerts"],
    queryFn: getCappingAlerts,
    enabled: allowed,
    staleTime: 60_000,
    retry: false,
  });
  if (!allowed || !data || data.rows.length === 0) return null;

  const total = data.over + data.ahead;
  return (
    <section role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <IconAlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" aria-hidden="true" />
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-gray-900">Capping alert · manage the count</h3>
            <p className="mt-0.5 text-xs text-gray-600">
              {data.monthLabel}, day {data.day} of {data.daysInMonth}.{" "}
              {data.over > 0 && <b>{data.over} over the monthly cap. </b>}
              {data.ahead > 0 && <b>{data.ahead} marking faster than the cap allows so far.</b>}
            </p>
          </div>
        </div>
        <Link to="/capping" className="text-xs font-semibold text-brand-600 hover:text-brand-700">Open capping</Link>
      </div>
      <ul className="mt-3 space-y-1.5 text-sm text-gray-800">
        {data.rows.slice(0, SHOWN).map((r) => (
          <li key={r.storeId} className="flex flex-wrap items-baseline gap-x-2">
            <span className={`text-[11px] font-bold uppercase tracking-wide ${r.alert === "OVER" ? "text-status-danger" : "text-status-warning"}`}>
              {r.alert === "OVER" ? "Over" : "Ahead"}
            </span>
            <span className="font-semibold">{r.outletName}</span>
            <span className="text-xs text-gray-600">{line(r)}</span>
          </li>
        ))}
      </ul>
      {total > SHOWN && <p className="mt-2 text-xs text-gray-600">and {total - SHOWN} more in Capping.</p>}
    </section>
  );
}
