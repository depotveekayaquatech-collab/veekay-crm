import { IconAlertTriangle } from "@/components/ui/icons";
import { dateLabel, fmtAvg } from "@/features/capping/helpers";
import type { CapSummary } from "@/services/capping";

/** Red banner at the top of the Zepto Capping page when the COLLECTIVE average entry or the COLLECTIVE average capping (all stores together) is above the limit.
 * A single store above the limit does not raise it. Nothing when both are within the limit. */
export function ReduceCappingBanner({ summary }: { summary: CapSummary | undefined }) {
  const o = summary?.overall;
  if (!summary || !o || !o.alert) return null;

  return (
    <section role="alert" className="rounded-xl border border-status-danger/40 bg-status-danger/5 p-4 shadow-card sm:p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-status-danger/15 text-status-danger">
          <IconAlertTriangle className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h3 className="text-base font-extrabold text-status-danger">Reduce capping</h3>
          <p className="text-xs text-gray-600">
            {o.entryBreach && o.entryAverage !== null && <>The average entry across all stores is <b className="tabular-nums">{fmtAvg(o.entryAverage)}</b>. </>}
            {o.cappingBreach && o.cappingAverage !== null && <>The average capping across all stores is <b className="tabular-nums">{fmtAvg(o.cappingAverage)}</b>. </>}
            The limit is {summary.limit} · {dateLabel(summary.from)} to {dateLabel(summary.to)}
          </p>
        </div>
      </div>
    </section>
  );
}
