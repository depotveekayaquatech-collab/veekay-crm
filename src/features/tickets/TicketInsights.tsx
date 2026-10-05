import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconAlertTriangle } from "@/components/ui/icons";
import { SegmentedControl, StatCard } from "@/features/orders/ui";
import { useTicketAnalytics } from "@/features/tickets/useTickets";
import { CATEGORY_LABEL, type Bucket } from "@/types/ticket";

const ROW_TINT = { ok: "", medium: "bg-status-warning-soft/50", high: "bg-status-danger-soft/60" } as const;

/** One bar per region / state / vendor: active tickets, overdue ones in red, problem areas highlighted. */
function BucketChart({ title, hint, rows, empty }: { title: string; hint: string; rows: Bucket[]; empty: string }) {
  const max = Math.max(1, ...rows.map((r) => r.active));
  return (
    <section className="flex flex-col overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card">
      <div className="border-b border-surface-border px-4 py-3.5 sm:px-5">
        <h3 className="text-sm font-bold text-heading">{title}</h3>
        <p className="text-xs text-gray-500">{hint}</p>
      </div>
      {rows.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-gray-500">{empty}</p>
      ) : (
        <ul className="divide-y divide-surface-border">
          {rows.map((r) => {
            const onTime = r.active - r.overdue;
            return (
              <li key={r.label} className={`grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 px-4 py-2.5 sm:px-5 ${ROW_TINT[r.severity]}`}>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-gray-900" title={r.label}>{r.label}</p>
                  {r.severity === "high" && (
                    <p className="flex items-center gap-1 text-[11px] font-semibold text-status-danger">
                      <IconAlertTriangle className="h-3 w-3" /> Needs attention
                    </p>
                  )}
                </div>
                <div className="flex h-2.5 overflow-hidden rounded-full bg-surface-muted" role="img" aria-label={`${r.active} active, ${r.overdue} overdue`}>
                  <div className="bg-status-danger" style={{ width: `${(r.overdue / max) * 100}%` }} />
                  <div className="bg-brand-500" style={{ width: `${(onTime / max) * 100}%` }} />
                </div>
                <div className="flex items-center gap-1.5 text-xs tabular-nums text-gray-600">
                  <span className="font-bold text-gray-900">{r.active}</span>
                  <span className="text-gray-400">active</span>
                  {r.delivery > 0 && <Badge tone="danger">{r.delivery} late</Badge>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Trend({ data }: { data: { label: string; created: number; resolved: number }[] }) {
  const max = Math.max(1, ...data.flatMap((d) => [d.created, d.resolved]));
  return (
    <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-heading">Last 14 days</h3>
        <div className="flex gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-brand-500" /> Raised</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-status-success" /> Resolved</span>
        </div>
      </div>
      <div className="mt-4 flex h-32 items-end gap-1.5" role="img" aria-label="Tickets raised and resolved per day">
        {data.map((d) => (
          <div key={d.label} className="flex h-full min-w-0 flex-1 flex-col justify-end gap-1" title={`${d.label}: ${d.created} raised, ${d.resolved} resolved`}>
            <div className="flex flex-1 items-end justify-center gap-0.5">
              <div className="w-1/2 max-w-3 rounded-t bg-brand-500" style={{ height: `${(d.created / max) * 100}%`, minHeight: d.created ? 3 : 0 }} />
              <div className="w-1/2 max-w-3 rounded-t bg-status-success" style={{ height: `${(d.resolved / max) * 100}%`, minHeight: d.resolved ? 3 : 0 }} />
            </div>
            <span className="truncate text-center text-[9px] text-gray-400">{d.label.split(" ")[1]}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function TicketInsights() {
  const [days, setDays] = useState(30);
  const { data, isLoading, isError, refetch } = useTicketAnalytics(days, true);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="Period"
          value={String(days)}
          onChange={(v) => setDays(Number(v))}
          options={[
            { value: "7", label: "7 days" },
            { value: "30", label: "30 days" },
            { value: "90", label: "90 days" },
          ]}
        />
        <p className="text-xs text-gray-500">Open tickets are always counted, whatever their age.</p>
      </div>

      {isLoading && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
          <Skeleton className="h-72" />
        </>
      )}
      {isError && <ErrorState message="Couldn't load ticket insights." onRetry={() => refetch()} />}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Active tickets" value={data.summary.open + data.summary.inProgress} hint={`${data.summary.open} open · ${data.summary.inProgress} in progress`} tone="brand" />
            <StatCard
              label="Overdue"
              value={data.summary.overdue}
              hint="past their deadline"
              tone="warning"
              valueClassName={data.summary.overdue ? "text-status-danger" : "text-status-success"}
            />
            <StatCard
              label="Delivery problems"
              value={data.summary.deliveryActive}
              hint="late or missed deliveries, unresolved"
              tone="aqua"
              valueClassName={data.summary.deliveryActive ? "text-status-warning" : "text-status-success"}
            />
            <StatCard
              label="Resolved"
              value={data.summary.resolved}
              hint={`of ${data.summary.raised} raised${data.summary.avgResolutionHours !== null ? ` · avg ${data.summary.avgResolutionHours} h` : ""}`}
              tone="success"
            />
          </div>

          <div className="grid gap-5 xl:grid-cols-3">
            <BucketChart title="By region" hint="Where tickets are piling up" rows={data.byRegion} empty="No tickets yet." />
            <BucketChart title="By state" hint="Top states by unresolved tickets" rows={data.byState} empty="No tickets yet." />
            <BucketChart title="By vendor" hint="Vendors whose stores keep raising issues" rows={data.byVendor} empty="No tickets yet." />
          </div>

          <div className="grid gap-5 xl:grid-cols-[2fr_1fr]">
            <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card">
              <div className="border-b border-surface-border px-4 py-3.5 sm:px-5">
                <h3 className="text-sm font-bold text-heading">Stores to look at first</h3>
                <p className="text-xs text-gray-500">Ranked by overdue and late-delivery tickets</p>
              </div>
              {data.hotspots.length === 0 ? (
                <p className="px-5 py-10 text-center text-sm text-gray-500">No store has an unresolved problem. 🎉</p>
              ) : (
                <div className="stacked-table overflow-x-auto">
                  <table className="w-full min-w-[640px] text-sm">
                    <thead>
                      <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        <th className="px-5 py-2.5">Store</th>
                        <th className="px-4 py-2.5">Region · State</th>
                        <th className="px-4 py-2.5">Vendor</th>
                        <th className="px-4 py-2.5 text-right">Active</th>
                        <th className="px-4 py-2.5 text-right">Late</th>
                        <th className="px-4 py-2.5 text-right">Overdue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.hotspots.map((h) => (
                        <tr key={h.storeId} className={`border-b border-surface-border last:border-0 ${h.overdue ? "bg-status-danger-soft/40" : ""}`}>
                          <td className="px-5 py-2.5" data-label="Store">
                            <div className="font-medium text-gray-900">{h.name}</div>
                            <div className="text-xs text-gray-500">{h.code} · {h.platformName}</div>
                          </td>
                          <td className="px-4 py-2.5 text-gray-700" data-label="Region · State">{[h.regionName, h.state].filter(Boolean).join(" · ") || "—"}</td>
                          <td className="px-4 py-2.5 text-gray-700" data-label="Vendor">{h.vendorName ?? "—"}</td>
                          <td className="px-4 py-2.5 text-right font-semibold tabular-nums" data-label="Active">{h.active}</td>
                          <td className="px-4 py-2.5 text-right tabular-nums" data-label="Late">{h.delivery ? <Badge tone="danger">{h.delivery}</Badge> : "—"}</td>
                          <td className="px-4 py-2.5 text-right tabular-nums" data-label="Overdue">{h.overdue ? <Badge tone="danger">{h.overdue}</Badge> : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <div className="flex flex-col gap-5">
              <Trend data={data.trend} />
              <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card sm:p-5">
                <h3 className="text-sm font-bold text-heading">What goes wrong</h3>
                {data.byCategory.length === 0 ? (
                  <p className="mt-3 text-sm text-gray-500">Nothing raised in this period.</p>
                ) : (
                  <ul className="mt-3 flex flex-col gap-2.5">
                    {data.byCategory.map((c) => {
                      const top = data.byCategory[0].count;
                      const delivery = c.category === "LATE_DELIVERY" || c.category === "NO_DELIVERY";
                      return (
                        <li key={c.category} className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-2.5 text-sm">
                          <span className="truncate text-gray-700">{CATEGORY_LABEL[c.category]}</span>
                          <span className="h-2 overflow-hidden rounded-full bg-surface-muted">
                            <span className={`block h-full rounded-full ${delivery ? "bg-status-danger" : "bg-aqua-400"}`} style={{ width: `${(c.count / top) * 100}%` }} />
                          </span>
                          <span className="font-semibold tabular-nums text-gray-900">{c.count}</span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
