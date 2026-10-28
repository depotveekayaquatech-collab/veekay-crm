import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { fmtAvg } from "@/features/capping/helpers";
import type { CapAlert, CapTone } from "@/services/capping";

const TONE: Record<CapTone, { card: string; value: string }> = {
  ok: { card: "border-status-success/40 bg-status-success/5", value: "text-status-success" },
  warn: { card: "border-status-warning/50 bg-status-warning/5", value: "text-status-warning" },
  over: { card: "border-status-danger/50 bg-status-danger/5", value: "text-status-danger" },
  none: { card: "border-surface-border bg-surface", value: "text-gray-500" },
};

/** The two averages the alert is based on, all stores together: green under the limit by more than the margin, amber within the margin of it, red above it. */
export function AverageCards({ alert, isLoading, error, onRetry }: { alert: CapAlert | undefined; isLoading: boolean; error: Error | null; onRetry: () => void }) {
  if (isLoading) return <Skeleton className="h-28" />;
  if (error) return <ErrorState message={error.message || "Couldn't load the averages."} onRetry={onRetry} />;
  if (!alert) return null;
  const o = alert.overall;
  const t = TONE[o.status];
  const big = (label: string, v: number | null, breach: boolean, days: number, unit: string) => (
    <div className={`rounded-xl border p-4 shadow-card ${breach ? TONE.over.card : t.card}`}>
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      <p className={`mt-1 text-3xl font-extrabold tabular-nums ${breach ? TONE.over.value : t.value}`}>
        {v === null ? "—" : fmtAvg(v)} <span className="text-base font-semibold text-gray-500">/ Limit {alert.limit}</span>
      </p>
      <p className="text-xs text-gray-600">{v === null ? "Nothing to average yet" : `${days.toLocaleString("en-IN")} ${unit}`}</p>
    </div>
  );
  return (
    <section className="grid gap-3 sm:grid-cols-2" aria-label="Average against the limit">
      {big("Average entry · all stores", o.entryAverage, o.entryBreach, o.entryDays, "store-days with an entry")}
      {big("Average capping · all stores", o.cappingAverage, o.cappingBreach, o.cappingDays, "store-days with a capping")}
    </section>
  );
}
