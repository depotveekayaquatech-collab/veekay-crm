import { distinctOptions } from "@/lib/options";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { IconDownload, IconRefresh } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { usePartners } from "@/features/stores/useStores";
import { useDailyOverview } from "@/features/orders/useOrders";
import { Avatar, ProgressBar, RegionFilter, SearchBox, SegmentedControl, StatCard } from "@/features/orders/ui";

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
  const [region, setRegion] = useState("");
  const regions = useMemo(
    () => distinctOptions(data?.employees ?? [], (e) => (e.regionName ? { value: e.regionName, label: e.regionName } : null)),
    [data],
  );
  const [behindOnly, setBehindOnly] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => void refetch(), 60_000);
    return () => clearInterval(id);
  }, [autoRefresh, refetch]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.employees ?? [])
      .filter(
        (e) =>
          (!behindOnly || e.percent < 50) &&
          (!region || e.regionName === region) &&
          (!q ||
            e.employeeName.toLowerCase().includes(q) ||
            e.employeeCode.toLowerCase().includes(q) ||
            (e.regionName ?? "").toLowerCase().includes(q)),
      )
      .sort((a, b) => a.percent - b.percent || a.employeeName.localeCompare(b.employeeName));
  }, [data, query, behindOnly, region]);

  const totals = useMemo(() => {
    const emps = (data?.employees ?? []).filter((e) => !region || e.regionName === region);
    const stores = emps.reduce((s, e) => s + e.totalStores, 0);
    const done = emps.reduce((s, e) => s + e.entriesDone, 0);
    return {
      bottles: emps.reduce((s, e) => s + e.bottles, 0),
      done,
      stores,
      percent: stores ? Math.round((done / stores) * 100) : 0,
      behind: emps.filter((e) => e.percent < 50).length,
    };
  }, [data, region]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="Platform"
          value={activePartner}
          onChange={(v) => {
            setPartner(v);
            setRegion("");
          }}
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
        />
        {regions.length > 1 && <RegionFilter value={region} onChange={setRegion} options={regions} className="sm:w-48 [&_label]:sr-only" />}
        <div className="ml-auto">
          <SegmentedControl
            label="Day"
            value={String(dayOffset)}
            onChange={(v) => setDayOffset(Number(v))}
            options={[
              { value: "0", label: "Today" },
              { value: "1", label: "Yesterday" },
            ]}
          />
        </div>
      </div>

      {isLoading && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}
          </div>
          <Skeleton className="h-64" />
        </>
      )}
      {isError && <ErrorState message="Couldn't load the overview." onRetry={() => refetch()} />}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <p className="text-sm text-gray-500">
              <span className="font-semibold text-gray-800">{data.partnerLabel}</span> · {data.dateLabel} ({data.date})
              {dataUpdatedAt ? ` · updated ${new Date(dataUpdatedAt).toLocaleTimeString()}` : ""}
            </p>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-gray-600">
                <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="accent-brand-500" />
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
            <StatCard label="Bottles marked" value={totals.bottles.toLocaleString()} tone="brand" />
            <StatCard label="Entries done" value={`${totals.done} / ${totals.stores}`} tone="aqua" />
            <StatCard label="Completion" value={`${totals.percent}%`} tone="success">
              <ProgressBar percent={totals.percent} className="mt-3" />
            </StatCard>
            <StatCard
              label="Behind schedule"
              value={totals.behind}
              hint={totals.behind > 0 ? "employees under 50%" : "everyone is on track"}
              tone="warning"
              valueClassName={totals.behind > 0 ? "text-status-warning" : "text-status-success"}
            />
          </div>

          <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card">
            <div className="flex flex-wrap items-center gap-3 border-b border-surface-border px-4 py-3.5 sm:px-5">
              <h3 className="text-sm font-bold text-heading">Employees <span className="ml-1 font-medium text-gray-400">{rows.length}</span></h3>
              <div className="ml-auto flex flex-wrap items-center gap-3">
                <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-600">
                  <input type="checkbox" checked={behindOnly} onChange={(e) => setBehindOnly(e.target.checked)} className="accent-brand-500" />
                  Behind only (&lt; 50%)
                </label>
                <SearchBox value={query} onChange={setQuery} placeholder="Search employee, code or region" className="w-full sm:w-72" />
              </div>
            </div>
            <div className="stacked-table overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-5 py-3">Employee</th>
                    <th className="px-4 py-3">Stores</th>
                    <th className="px-4 py-3">Bottles</th>
                    <th className="w-64 px-4 py-3">Progress</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-12 text-center text-gray-500">No employees match.</td></tr>
                  )}
                  {rows.map((e) => (
                    <tr key={e.employeeId} className="border-b border-surface-border last:border-0">
                      <td className="px-5 py-3" data-label="Employee">
                        <div className="flex items-center gap-3">
                          <Avatar name={e.employeeName} />
                          <div className="min-w-0">
                            <div className="truncate font-medium text-gray-900">{e.employeeName}</div>
                            <div className="text-xs text-gray-500">
                              {e.employeeCode}{e.regionName ? ` · ${e.regionName}` : ""}
                            </div>
                            {e.error && <div className="text-xs text-status-warning">{e.error}</div>}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 tabular-nums" data-label="Stores">
                        {e.entriesDone} <span className="text-gray-400">/ {e.totalStores}</span>
                      </td>
                      <td className="px-4 py-3 font-semibold tabular-nums" data-label="Bottles">{e.bottles}</td>
                      <td className="px-4 py-3" data-label="Progress">
                        <div className="flex items-center gap-3">
                          <ProgressBar percent={e.percent} className="min-w-[6rem] flex-1" />
                          <Badge tone={pctTone(e.percent)}>{e.percent}%</Badge>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card">
            <div className="border-b border-surface-border px-4 py-3.5 sm:px-5">
              <h3 className="text-sm font-bold text-heading">Recent submissions</h3>
            </div>
            <div className="stacked-table max-h-96 overflow-auto">
              <table className="w-full min-w-[600px] text-sm">
                <thead className="sticky top-0 bg-surface-subtle">
                  <tr className="border-b border-surface-border text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-5 py-2.5">When</th>
                    <th className="px-4 py-2.5">Employee</th>
                    <th className="px-4 py-2.5">Store</th>
                    <th className="px-4 py-2.5">Order date</th>
                    <th className="px-4 py-2.5 text-right">Bottles</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recentSubmissions.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-10 text-center text-gray-500">No submissions yet.</td></tr>
                  )}
                  {data.recentSubmissions.map((s) => (
                    <tr key={s.id} className="border-b border-surface-border last:border-0">
                      <td className="px-5 py-2.5 text-gray-500" data-label="When">{new Date(s.submittedAt).toLocaleString()}</td>
                      <td className="px-4 py-2.5" data-label="Employee">
                        {s.employeeName ?? "—"}
                        {s.source === "admin" && <span className="ml-2"><Badge tone="warning">admin</Badge></span>}
                      </td>
                      <td className="px-4 py-2.5" data-label="Store">{s.storeName} <span className="text-gray-400">{s.storeCode}</span></td>
                      <td className="px-4 py-2.5" data-label="Order date">{s.orderDate}</td>
                      <td className="px-4 py-2.5 text-right font-semibold tabular-nums" data-label="Bottles">{s.bottleCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
