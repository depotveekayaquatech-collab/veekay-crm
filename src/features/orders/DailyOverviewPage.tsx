import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { usePartners } from "@/features/stores/useStores";
import { useDailyOverview } from "@/features/orders/useOrders";

function pctTone(p: number): "success" | "warning" | "danger" {
  return p >= 85 ? "success" : p >= 50 ? "warning" : "danger";
}

export function DailyOverviewPage() {
  const { data: partners = [] } = usePartners();
  const [partner, setPartner] = useState("");
  const [dayOffset, setDayOffset] = useState(0);

  const activePartner = partner || partners[0]?.slug || "";
  const { data, isLoading, isError, refetch } = useDailyOverview(activePartner, dayOffset);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Daily overview"
        subtitle="Per-employee marking progress, live from today's entries."
      />

      <div className="flex flex-wrap items-center gap-2">
        {partners.map((p) => (
          <button
            key={p.slug}
            onClick={() => setPartner(p.slug)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              activePartner === p.slug
                ? "bg-brand-500 text-white"
                : "bg-white text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
            }`}
          >
            {p.name}
          </button>
        ))}
        <div className="ml-auto">
          <Select
            label=""
            aria-label="Day"
            value={String(dayOffset)}
            onChange={(e) => setDayOffset(Number(e.target.value))}
            options={[
              { value: "0", label: "Today" },
              { value: "1", label: "Yesterday" },
            ]}
          />
        </div>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load the overview." onRetry={() => refetch()} />}

      {data && (
        <>
          <p className="text-sm text-gray-500">
            {data.partnerLabel} · {data.dateLabel} ({data.date})
          </p>

          {/* Responsive: table on desktop, stacked cards on mobile */}
          <div className="stacked-table overflow-x-auto rounded-lg border border-surface-border bg-white shadow-card">
            <table className="w-full min-w-[600px] text-sm">
              <thead>
                <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  <th className="px-4 py-3">Employee</th>
                  <th className="px-4 py-3">Stores</th>
                  <th className="px-4 py-3">Entries done</th>
                  <th className="px-4 py-3">Bottles</th>
                  <th className="px-4 py-3">Completion</th>
                </tr>
              </thead>
              <tbody>
                {data.employees.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-10 text-center text-gray-500">No employees on this platform.</td></tr>
                )}
                {data.employees.map((e) => (
                  <tr key={e.employeeId} className="border-b border-surface-border">
                    <td className="px-4 py-3" data-label="Employee">
                      <div className="font-medium text-gray-900">
                        {e.error ? "⚠️ " : ""}{e.employeeName}
                      </div>
                      {e.regionName && <div className="text-xs text-gray-500">{e.regionName}</div>}
                      {e.error && <div className="text-xs text-status-warning">{e.error}</div>}
                    </td>
                    <td className="px-4 py-3" data-label="Stores">{e.totalStores}</td>
                    <td className="px-4 py-3" data-label="Entries done">{e.entriesDone} / {e.totalStores}</td>
                    <td className="px-4 py-3 tabular-nums" data-label="Bottles">{e.bottles}</td>
                    <td className="px-4 py-3" data-label="Completion">
                      <Badge tone={pctTone(e.percent)}>{e.percent}%</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-lg border border-surface-border bg-white shadow-card">
            <div className="border-b border-surface-border px-4 py-3 text-sm font-semibold text-gray-900">
              Recent submissions
            </div>
            <div className="stacked-table max-h-96 overflow-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-4 py-2.5">When</th>
                    <th className="px-4 py-2.5">Employee</th>
                    <th className="px-4 py-2.5">Store</th>
                    <th className="px-4 py-2.5">Order date</th>
                    <th className="px-4 py-2.5">Bottles</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recentSubmissions.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">No submissions yet.</td></tr>
                  )}
                  {data.recentSubmissions.map((s) => (
                    <tr key={s.id} className="border-b border-surface-border">
                      <td className="px-4 py-2.5 text-gray-500" data-label="When">{new Date(s.submittedAt).toLocaleString()}</td>
                      <td className="px-4 py-2.5" data-label="Employee">{s.employeeName ?? "—"}</td>
                      <td className="px-4 py-2.5" data-label="Store">{s.storeName} <span className="text-gray-400">{s.storeCode}</span></td>
                      <td className="px-4 py-2.5" data-label="Order date">{s.orderDate}</td>
                      <td className="px-4 py-2.5 tabular-nums" data-label="Bottles">{s.bottleCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
