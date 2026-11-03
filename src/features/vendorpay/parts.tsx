import { Link } from "react-router-dom";
import { Skeleton } from "@/components/feedback/Skeleton";
import { inr } from "@/features/cash/api";
import { ageText, formatWhen } from "@/features/vendorpay/format";
import type { Freshness, Money } from "@/features/vendorpay/api";

/** A rupee amount. Negative values (paid more than billed) get a text hint, never colour alone. */
export function Amount({ value, strong = false }: { value: Money; strong?: boolean }) {
  const negative = Number(value) < 0;
  return (
    <span className={`tabular-nums ${strong ? "font-bold text-heading" : ""} ${negative ? "text-status-warning" : ""}`} title={negative ? "Paid more than billed" : undefined}>
      {inr(value)}
    </span>
  );
}

export function Stat({ label, value, hint, loading }: { label: string; value: Money | null; hint?: string; loading?: boolean }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface px-4 py-3 shadow-card">
      <p className="text-[11px] font-bold text-gray-500">{label}</p>
      {loading || value === null ? <Skeleton className="mt-2 h-7 w-28" /> : <p className="mt-1 text-xl font-bold text-heading"><Amount value={value} /></p>}
      {hint && <p className="mt-0.5 text-[11px] text-gray-500">{hint}</p>}
    </div>
  );
}

/** "Last updated" line, turning into a warning once the data is older than the server's limit. */
export function FreshnessBanner({ freshness, canManage }: { freshness: Freshness | undefined; canManage: boolean }) {
  if (!freshness) return <Skeleton className="h-10 w-full" />;
  const manage = canManage ? (
    <Link to="/vendor-payments/admin" className="ml-2 font-semibold underline">
      Sync history
    </Link>
  ) : null;

  if (freshness.neverSynced) {
    return (
      <div role="status" className="rounded-xl bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
        No data has been received from Busy yet, so the figures below are empty or incomplete.{manage}
      </div>
    );
  }
  const when = freshness.lastUpdated ? formatWhen(freshness.lastUpdated) : "";
  const ago = freshness.ageMinutes !== null ? ` (${ageText(freshness.ageMinutes)})` : "";
  if (freshness.stale) {
    return (
      <div role="alert" className="rounded-xl bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
        <span className="font-bold">The data may be out of date.</span> The last update from Busy was {when}
        {ago}, more than {freshness.staleHours} hours ago.{manage}
      </div>
    );
  }
  return (
    <p className="text-sm text-gray-500">
      Last updated: <span className="font-semibold text-gray-700">{when}</span>
      {ago}
      {manage}
    </p>
  );
}
