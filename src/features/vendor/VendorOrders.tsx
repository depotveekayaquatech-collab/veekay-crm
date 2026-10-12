import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EmptyState } from "@/components/feedback/EmptyState";
import { daysAgo } from "@/lib/dates";
import { useDailyOrders, useOrders } from "@/features/vendor/useVendorData";
import { ErrorNote, ListSkeleton, StoreSelect } from "@/features/vendor/parts";
import { fmtDate } from "@/features/vendor/format";

const RANGES = [
  { label: "7 days", days: 6 },
  { label: "31 days", days: 30 },
  { label: "3 months", days: 90 },
];

/** The stores behind one day's total; fetched only when the day is opened. */
function DayStores({ day, store }: { day: string; store: string }) {
  const q = useOrders({ store_id: store || undefined, date_from: day, date_to: day, page_size: 200 });
  if (q.isLoading) return <div className="px-4 py-3 text-sm text-gray-500">Loading…</div>;
  if (q.isError) return <div className="px-4 py-3"><ErrorNote message={q.error.message} onRetry={() => q.refetch()} /></div>;
  return (
    <ul className="divide-y divide-surface-border border-t border-surface-border bg-surface-subtle">
      {q.data!.items.map((r) => (
        <li key={r.store_id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
          <span className="min-w-0 truncate text-gray-800">{r.store_name}</span>
          <span className="shrink-0 font-semibold text-gray-900">{r.bottle_count}</span>
        </li>
      ))}
    </ul>
  );
}

export function VendorOrders() {
  const [params, setParams] = useSearchParams();
  const store = params.get("store") ?? "";
  const [days, setDays] = useState(30);
  const [open, setOpen] = useState<string | null>(null);
  const q = useDailyOrders({ store_id: store || undefined, date_from: daysAgo(days), date_to: daysAgo(0) });

  const total = q.data?.reduce((n, d) => n + d.bottles, 0) ?? 0;
  const best = q.data?.reduce((m, d) => Math.max(m, d.bottles), 0) ?? 0;

  return (
    <div>
      <h1 className="text-xl font-bold text-heading">Orders</h1>
      <p className="text-sm text-gray-500">Bottles delivered each day. Tap a day to see the stores.</p>

      <div className="mt-4 flex flex-col gap-3">
        <StoreSelect value={store} allLabel="All my stores" label="Showing" onChange={(v) => { setParams(v ? { store: v } : {}, { replace: true }); setOpen(null); }} />
        <div className="flex gap-2" role="group" aria-label="Period">
          {RANGES.map((r) => (
            <button
              key={r.days}
              type="button"
              aria-pressed={days === r.days}
              onClick={() => { setDays(r.days); setOpen(null); }}
              className={`h-10 flex-1 rounded-xl border text-sm font-semibold ${days === r.days ? "border-brand-600 bg-brand-600 text-white" : "border-surface-border bg-surface text-gray-600"}`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {q.data && q.data.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-surface-border bg-surface p-3.5 shadow-sm">
            <p className="text-xs text-gray-500">Total bottles</p>
            <p className="mt-1 text-2xl font-bold text-heading">{total.toLocaleString("en-IN")}</p>
          </div>
          <div className="rounded-2xl border border-surface-border bg-surface p-3.5 shadow-sm">
            <p className="text-xs text-gray-500">Daily average</p>
            <p className="mt-1 text-2xl font-bold text-heading">{Math.round(total / q.data.length).toLocaleString("en-IN")}</p>
          </div>
        </div>
      )}

      <div className="mt-4">
        {q.isLoading ? (
          <ListSkeleton />
        ) : q.isError ? (
          <ErrorNote message={q.error.message} onRetry={() => q.refetch()} />
        ) : q.data!.length === 0 ? (
          <EmptyState title="No orders in this period" description="Daily counts appear here once stores are marked." />
        ) : (
          <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-sm">
            {q.data!.map((d) => {
              const isOpen = open === d.order_date;
              return (
                <div key={d.order_date} className="border-b border-surface-border last:border-0">
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? null : d.order_date)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-surface-subtle"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-gray-900">{fmtDate(d.order_date)}</span>
                      <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-surface-muted">
                        <span className="block h-full rounded-full bg-brand-500" style={{ width: `${best ? (d.bottles / best) * 100 : 0}%` }} />
                      </span>
                    </span>
                    <span className="w-20 shrink-0 text-right">
                      <span className="block text-base font-bold text-gray-900">{d.bottles.toLocaleString("en-IN")}</span>
                      <span className="block text-[11px] text-gray-500">{d.stores} store{d.stores === 1 ? "" : "s"}</span>
                    </span>
                    <span aria-hidden className={`shrink-0 text-gray-400 transition-transform ${isOpen ? "rotate-180" : ""}`}>▾</span>
                  </button>
                  {isOpen && <DayStores day={d.order_date} store={store} />}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
