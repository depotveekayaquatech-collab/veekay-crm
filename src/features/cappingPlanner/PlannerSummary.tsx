import type { ReactNode } from "react";
import type { PlanTotals } from "@/services/cappingPlanner";

const n = (v: number) => v.toLocaleString("en-IN");

function Card({ label, value, sub, tone = "text-gray-900" }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-xl border border-surface-border bg-surface p-4 shadow-card">
      <span className="text-[11px] font-bold text-gray-500">{label}</span>
      <span className={`break-words text-2xl font-extrabold tabular-nums ${tone}`}>{value}</span>
      {sub && <span className="text-xs text-gray-500">{sub}</span>}
    </div>
  );
}

/** The six headline figures. Before the first calculation they show a dash, never a made-up number. */
export function PlannerCards({ totals }: { totals: PlanTotals | null }) {
  const t = totals;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-6" aria-label="Plan summary">
      <Card label="Total stores" value={t ? n(t.stores) : "—"} sub={t ? `${n(t.eligible)} verified with capacity` : undefined} />
      <Card label="Stores selected" value={t ? n(t.selected) : "—"} sub={t?.storeLimit ? `limit ${n(t.storeLimit)}` : t ? "no limit" : undefined} />
      <Card label="Available capacity" value={t ? n(t.availableCapacity) : "—"} sub={t ? `${n(t.selectedCapacity)} in the selected stores` : undefined} tone="text-status-success" />
      <Card label="Target difference" value={t ? n(t.target) : "—"} sub={t ? `current ${n(t.currentTotal)} → desired ${n(t.desiredTotal)}` : undefined} />
      <Card label="Planned match" value={t ? n(t.matchable) : "—"} sub={t?.percentCovered != null ? `${t.percentCovered}% of the target` : undefined} tone="text-brand-600" />
      <Card label="Unmatched difference" value={t ? n(t.unmatched) : "—"} sub={t ? `${n(t.unusedCapacity)} capacity left unused` : undefined} tone={t && t.unmatched > 0 ? "text-status-danger" : "text-gray-900"} />
    </div>
  );
}

function Banner({ tone, title, children }: { tone: "success" | "warning" | "danger" | "neutral"; title: string; children: ReactNode }) {
  const cls = {
    success: "border-status-success/40 bg-status-success/5",
    warning: "border-status-warning/50 bg-status-warning/5",
    danger: "border-status-danger/50 bg-status-danger/5",
    neutral: "border-surface-border bg-surface-subtle/60",
  }[tone];
  return (
    <section role="status" className={`rounded-xl border p-4 shadow-card ${cls}`}>
      <h3 className="text-sm font-extrabold text-gray-900">{title}</h3>
      <p className="mt-1 text-sm text-gray-700">{children}</p>
    </section>
  );
}

/** Whether the target fits, in words: fits, only partly fits (and how many stores it would take), or cannot be covered at all. */
export function Feasibility({ totals: t }: { totals: PlanTotals }) {
  if (t.target === 0) return <Banner tone="neutral" title="No target entered">Enter the target difference to see whether it fits. The capacity above is what the stores could still take.</Banner>;
  if (t.fits) {
    return (
      <Banner tone="success" title="The target fits within the selected stores' capacity">
        {n(t.target)} of {n(t.selectedCapacity)} available capacity in {n(t.selected)} stores; {n(t.unusedCapacity)} capacity would be left unused.
      </Banner>
    );
  }
  if (!t.coverable) {
    return (
      <Banner tone="danger" title="The target cannot be covered by any number of stores">
        Every verified store together has only {n(t.availableCapacity)} capacity, so {n(t.target - t.availableCapacity)} would stay unmatched. Nothing is added to make it match.
      </Banner>
    );
  }
  return (
    <Banner tone="warning" title="Only part of the target fits in the selected stores">
      {n(t.matchable)} of {n(t.target)} ({t.percentCovered}%) fits in {n(t.selected)} stores; {n(t.unmatched)} remains unmatched.
      {t.storesRequired ? ` Using ${n(t.storesRequired)} stores in this order would cover it.` : ""}
    </Banner>
  );
}
