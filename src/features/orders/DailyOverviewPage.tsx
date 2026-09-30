import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { IconDownload, IconRefresh, IconSearch } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
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
  const { data, isLoading, isError, refetch, isFetching, dataUpdatedAt } = useDailyOverview(activePartner, dayOffset);
  const [query, setQuery] = useState("");
  const [behindOnly, setBehindOnly] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => void refetch(), 60_000);
    return () => clearInterval(id);
  }, [autoRefresh, refetch]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.employees ?? []).filter(
      (e) =>
        (!behindOnly || e.percent < 50) &&
        (!q ||
          e.employeeName.toLowerCase().includes(q) ||
          e.employeeCode.toLowerCase().includes(q) ||
          (e.regionName ?? "").toLowerCase().includes(q)),
    );
  }, [data, query, behindOnly]);

  const totals = useMemo(() => {
    const emps = data?.employees ?? [];
    const stores = emps.reduce((s, e) => s + e.totalStores, 0);
    const done = emps.reduce((s, e) => s + e.entriesDone, 0);
    return {
      bottles: emps.reduce((s, e) => s + e.bottles, 0),
      done,
      stores,
      percent: stores ? Math.round((done / stores) * 100) : 0,
      behind: emps.filter((e) => e.percent < 50).length,
    };
  }, [data]);

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
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <p className="text-sm text-gray-500">
              {data.partnerLabel} · {data.dateLabel} ({data.date})
              {dataUpdatedAt ? ` · updated ${new Date(dataUpdatedAt).toLocaleTimeString()}` : ""}
            </p>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-gray-600">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="accent-brand-500"
                />
                Auto-refresh (1 min)
              </label>
              <Button size="sm" variant="secondary" onClick={() => void refetch()} isLoading={isFetching}>
                <IconRefresh className="h-3.5 w-3.5" />
                Refresh
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={!rows.length}
                onClick={() =>
                  downloadCsv(
                    `daily-overview-${data.partnerSlug}-${data.date}.csv`,
                    ["Employee code", "Employee", "Region", "Stores", "Entries done", "Bottles", "Completion %"],
                    rows.map((e) => [e.employeeCode, e.employeeName, e.regionName, e.totalStores, e.entriesDone, e.bottles, e.percent]),
                  )
                }
              >
                <IconDownload className="h-3.5 w-3.5" />
                Export CSV
              </Button>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Bottles marked", value: totals.bottles, warn: false },
              { label: "Entries done", value: `${totals.done} / ${totals.stores}`, warn: false },
              { label: "Completion", value: `${totals.percent}%`, warn: false },
              { label: "Behind schedule", value: totals.behind, warn: totals.behind > 0 },
            ].map((k, i) => (
              <div key={k.label} className={`tile tile-${["brand", "aqua", "success", "warning"][i]} rounded-xl border border-surface-border bg-white p-4 shadow-card`}>
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{k.label}</p>
                <p className={`mt-1 text-2xl font-bold tabular-nums ${k.warn ? "text-status-warning" : "text-ink-900"}`}>
                  {k.value}
                </p>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-full sm:w-72">
              <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search employee, code or region"
                aria-label="Search employees"
                className="h-10 w-full rounded-lg border border-surface-border bg-white pl-9 pr-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
              />
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={behindOnly}
                onChange={(e) => setBehindOnly(e.target.checked)}
                className="accent-brand-500"
              />
              Behind schedule only (&lt; 50%)
            </label>
          </div>

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
                {rows.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-10 text-center text-gray-500">No employees match.</td></tr>
                )}
                {rows.map((e) => (
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
