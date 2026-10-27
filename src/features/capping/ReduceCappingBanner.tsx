import { useState } from "react";
import { IconAlertTriangle } from "@/components/ui/icons";
import { alertReasons, dateLabel } from "@/features/capping/helpers";
import type { CapSummary } from "@/services/capping";

const SHOWN = 8;

/** Red banner at the top of the Zepto Capping page: the stores whose average, or a single day, is above the limit, and why. Nothing when there are none. */
export function ReduceCappingBanner({ summary }: { summary: CapSummary | undefined }) {
  const [all, setAll] = useState(false);
  if (!summary) return null;
  const alerts = summary.rows.filter((r) => r.alert);
  if (alerts.length === 0) return null;
  const shown = all ? alerts : alerts.slice(0, SHOWN);

  return (
    <section role="alert" className="rounded-xl border border-status-danger/40 bg-status-danger/5 p-4 shadow-card sm:p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-status-danger/15 text-status-danger">
          <IconAlertTriangle className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h3 className="text-base font-extrabold text-status-danger">Reduce capping</h3>
          <p className="text-xs text-gray-600">
            {alerts.length} store{alerts.length === 1 ? " is" : "s are"} above the limit of {summary.limit} (average entry, average capping or a single day) · {dateLabel(summary.from)} to {dateLabel(summary.to)}
          </p>
        </div>
      </div>
      <ul className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {shown.map((r) => (
          <li key={r.storeId} className="rounded-lg border border-status-danger/25 bg-surface px-3 py-2">
            <p className="truncate text-sm font-bold text-gray-900" title={r.outletName}>{r.outletName}</p>
            <p className="text-xs font-medium text-status-danger">{alertReasons(r).join(" · ")}</p>
          </li>
        ))}
      </ul>
      {alerts.length > SHOWN && (
        <button type="button" className="mt-3 text-xs font-semibold text-brand-600 hover:text-brand-700" onClick={() => setAll((v) => !v)}>
          {all ? "Show fewer" : `Show all ${alerts.length} stores`}
        </button>
      )}
    </section>
  );
}
