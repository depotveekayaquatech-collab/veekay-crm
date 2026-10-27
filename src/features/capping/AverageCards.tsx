import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { IconSearch } from "@/components/ui/icons";
import { alertReasons, fmtAvg } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import type { CapOverall, CapSummary, CapSummaryRow, CapTone } from "@/services/capping";

const PAGE = 24;
const TONE: Record<CapTone, { card: string; value: string; label: string }> = {
  ok: { card: "border-status-success/40 bg-status-success/5", value: "text-status-success", label: "Within the limit" },
  warn: { card: "border-status-warning/50 bg-status-warning/5", value: "text-status-warning", label: "Close to the limit" },
  over: { card: "border-status-danger/50 bg-status-danger/5", value: "text-status-danger", label: "Above the limit" },
  none: { card: "border-surface-border bg-surface", value: "text-gray-500", label: "No entries" },
};

/** All stores together: the two averages the alert is based on. */
function Overall({ o, limit }: { o: CapOverall; limit: number }) {
  const t = TONE[o.status];
  const big = (label: string, v: number | null, breach: boolean, days: number, unit: string) => (
    <div className={`rounded-xl border p-4 shadow-card ${breach ? TONE.over.card : t.card}`}>
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      <p className={`mt-1 text-3xl font-extrabold tabular-nums ${breach ? TONE.over.value : t.value}`}>
        {v === null ? "—" : fmtAvg(v)} <span className="text-base font-semibold text-gray-500">/ Limit {limit}</span>
      </p>
      <p className="text-xs text-gray-600">{v === null ? "Nothing to average yet" : `${days.toLocaleString("en-IN")} ${unit}`}</p>
    </div>
  );
  return (
    <div className="grid gap-3 sm:grid-cols-2" aria-label="Collective averages">
      {big("Average entry · all stores", o.entryAverage, o.entryBreach, o.entryDays, "store-days with an entry")}
      {big("Average capping · all stores", o.cappingAverage, o.cappingBreach, o.cappingDays, "store-days with a capping")}
    </div>
  );
}

function Card({ row, limit }: { row: CapSummaryRow; limit: number }) {
  const t = TONE[row.status];
  return (
    <li className={`flex flex-col gap-1 rounded-xl border p-4 shadow-card ${t.card}`}>
      <p className="truncate text-sm font-bold text-gray-900" title={row.outletName}>{row.outletName}</p>
      <p className="truncate text-[11px] text-gray-500">{[row.outletId, row.city].filter(Boolean).join(" · ")}</p>
      <p className={`mt-1 text-xl font-extrabold tabular-nums ${row.averageBreach ? "text-status-danger" : t.value}`}>
        {row.average === null ? "No entries" : <>Avg {fmtAvg(row.average)} <span className="text-sm font-semibold text-gray-500">/ Limit {limit}</span></>}
      </p>
      <p className={`text-sm font-bold tabular-nums ${row.cappingBreach ? "text-status-danger" : "text-gray-700"}`}>
        {row.cappingAverage === null ? "No capping set" : <>Capping avg {fmtAvg(row.cappingAverage)} <span className="text-xs font-semibold text-gray-500">/ Limit {limit}</span></>}
      </p>
      <p className="text-xs text-gray-600">
        <span className={`font-semibold ${t.value}`}>{t.label}</span>
        {row.average !== null && <> · {row.entryDays} day{row.entryDays === 1 ? "" : "s"} · highest {row.maxDay}</>}
        {row.currentCapping !== null && <> · capping today {row.currentCapping}</>}
      </p>
      {row.alert && <p className="text-xs font-medium text-status-danger">{alertReasons(row).join(" · ")}</p>}
    </li>
  );
}

/** One card per store: its average daily entry against the limit. Green when the average is under the limit by more than the margin, amber when it is within
 * the margin of the limit (or exactly on it), red when the store is in alert (average or a single day above the limit). */
export function AverageCards({ summary, isLoading, error, onRetry }: { summary: CapSummary | undefined; isLoading: boolean; error: Error | null; onRetry: () => void }) {
  const [q, setQ] = useState("");
  const [onlyAlerts, setOnlyAlerts] = useState(false);
  const [shownCount, setShownCount] = useState(PAGE);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (summary?.rows ?? []).filter(
      (r) => (!onlyAlerts || r.status === "over" || r.status === "warn") && (!needle || r.outletName.toLowerCase().includes(needle) || r.outletId.toLowerCase().includes(needle)),
    );
  }, [summary, q, onlyAlerts]);

  return (
    <section className="flex flex-col gap-3" aria-label="Average against the limit">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-gray-900">Average against the limit</h3>
          <p className="text-xs text-gray-500">
            {summary ? `Limit ${summary.limit} bottles a day. The alert is on the collective averages of all stores together; the cards below show each store for reference.` : "Average daily entry and capping for the chosen month."}
          </p>
        </div>
        {summary && summary.rows.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative">
              <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input className={`${field} w-56 pl-9`} value={q} onChange={(e) => { setQ(e.target.value); setShownCount(PAGE); }} placeholder="Search store" aria-label="Search the cards" />
            </label>
            <button
              type="button"
              aria-pressed={onlyAlerts}
              onClick={() => { setOnlyAlerts((v) => !v); setShownCount(PAGE); }}
              className={`h-10 rounded-lg px-3 text-sm font-medium ${onlyAlerts ? "bg-brand-500 text-white" : "bg-surface-subtle text-gray-700 hover:bg-surface-border/60"}`}
            >
              Only red / amber
            </button>
          </div>
        )}
      </div>

      {isLoading && <Skeleton className="h-40" />}
      {error && <ErrorState message={error.message || "Couldn't load the averages."} onRetry={onRetry} />}
      {summary && summary.rows.length > 0 && <Overall o={summary.overall} limit={summary.limit} />}
      {summary && summary.rows.length === 0 && <EmptyState title="No stores yet" description="There are no live Zepto stores to measure." />}
      {summary && summary.rows.length > 0 && rows.length === 0 && <EmptyState title="No stores match" description="Change the search, or turn off “Only red / amber”." />}
      {summary && rows.length > 0 && (
        <>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {rows.slice(0, shownCount).map((r) => <Card key={r.storeId} row={r} limit={summary.limit} />)}
          </ul>
          {rows.length > shownCount && (
            <div className="flex justify-center">
              <Button variant="secondary" onClick={() => setShownCount((n) => n + PAGE)}>Show {Math.min(PAGE, rows.length - shownCount)} more ({rows.length - shownCount} left)</Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
