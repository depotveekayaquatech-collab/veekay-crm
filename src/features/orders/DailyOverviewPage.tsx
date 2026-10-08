import { distinctOptions } from "@/lib/options";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { IconCheckCircle, IconClipboard, IconDownload, IconRefresh, IconUsers } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { usePersistentState } from "@/hooks/usePersistentState";
import { usePartners } from "@/features/stores/useStores";
import { useDailyOverview } from "@/features/orders/useOrders";
import { Avatar, FilterChip, Panel, ProgressBar, ProgressRing, RegionFilter, SearchBox, SegmentedControl, StatCard } from "@/features/orders/ui";

type Sort = "behind" | "bottles" | "name";

function pctTone(p: number): "success" | "warning" | "danger" {
  return p >= 85 ? "success" : p >= 50 ? "warning" : "danger";
}

function timeAgo(ms: number, now: number): string {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  return `${Math.round(s / 60)}m ago`;
}

const MEDAL = ["from-amber-300 to-amber-500", "from-slate-300 to-slate-400", "from-orange-300 to-orange-500"];

export function DailyOverviewPage() {
  const { data: partners = [] } = usePartners();
  const [pickedPartner, setPartner] = usePersistentState<string>("orders.platform", "");
  const [dayOffset, setDayOffset] = useState(0);

  const activePartner = partners.some((p) => p.slug === pickedPartner) ? pickedPartner : (partners[0]?.slug ?? "");
  const { data, isLoading, isError, refetch, isFetching, dataUpdatedAt } = useDailyOverview(activePartner, dayOffset);
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("");
  const regions = useMemo(
    () => distinctOptions(data?.employees ?? [], (e) => (e.regionName ? { value: e.regionName, label: e.regionName } : null)),
    [data],
  );
  const [behindOnly, setBehindOnly] = useState(false);
  const [sort, setSort] = useState<Sort>("behind");
  const [autoRefresh, setAutoRefresh] = useState(false);
  // Ticks every 15s so "updated 2m ago" stays honest without refetching.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(id);
  }, []);

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
      .sort((a, b) =>
        sort === "bottles"
          ? b.bottles - a.bottles || a.employeeName.localeCompare(b.employeeName)
          : sort === "name"
            ? a.employeeName.localeCompare(b.employeeName)
            : a.percent - b.percent || a.employeeName.localeCompare(b.employeeName),
      );
  }, [data, query, behindOnly, region, sort]);

  const scoped = useMemo(() => (data?.employees ?? []).filter((e) => !region || e.regionName === region), [data, region]);
  const totals = useMemo(() => {
    const stores = scoped.reduce((s, e) => s + e.totalStores, 0);
    const done = scoped.reduce((s, e) => s + e.entriesDone, 0);
    return {
      bottles: scoped.reduce((s, e) => s + e.bottles, 0),
      done,
      stores,
      percent: stores ? Math.round((done / stores) * 100) : 0,
      behind: scoped.filter((e) => e.percent < 50).length,
    };
  }, [scoped]);
  const top = useMemo(() => [...scoped].filter((e) => e.bottles > 0).sort((a, b) => b.bottles - a.bottles).slice(0, 3), [scoped]);

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
          <Skeleton className="h-44 !rounded-2xl" />
          <div className="grid gap-4 sm:grid-cols-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 !rounded-2xl" />)}
          </div>
          <Skeleton className="h-64 !rounded-2xl" />
        </>
      )}
      {isError && <ErrorState message="Couldn't load the overview." onRetry={() => refetch()} />}

      {data && (
        <>
          <section className="relative overflow-hidden rounded-2xl border border-surface-border bg-surface p-4 shadow-card sm:p-6">
            <span aria-hidden="true" className="pointer-events-none absolute -right-12 -top-16 h-52 w-52 rounded-full bg-gradient-to-br from-brand-500/15 to-aqua-400/10 blur-2xl" />
            <div className="relative flex flex-wrap items-center gap-x-8 gap-y-5">
              <ProgressRing percent={totals.percent} size={128} sublabel="complete" />
              <div className="min-w-[14rem] flex-1">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-brand-600">{data.partnerLabel}</p>
                <h3 className="mt-0.5 text-xl font-extrabold text-heading">{data.dateLabel}</h3>
                <p className="mt-1 text-sm text-gray-500">
                  {totals.done} of {totals.stores} stores marked by {scoped.length} employees
                  {dataUpdatedAt ? ` · updated ${timeAgo(dataUpdatedAt, now)}` : ""}
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <label className="flex cursor-pointer items-center gap-2 rounded-full border border-surface-border px-3 py-1.5 text-xs font-semibold text-gray-600 hover:border-gray-300">
                    <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="accent-brand-500" />
                    Live (refresh every minute)
                  </label>
                  <Button size="sm" variant="secondary" onClick={() => void refetch()} isLoading={isFetching}>
                    <IconRefresh className="h-3.5 w-3.5" aria-hidden="true" />
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
                    <IconDownload className="h-3.5 w-3.5" aria-hidden="true" />
                    Export CSV
                  </Button>
                </div>
              </div>
            </div>
          </section>

          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Bottles marked" value={totals.bottles} tone="brand" icon={IconClipboard} />
            <StatCard label="Entries done" value={`${totals.done} / ${totals.stores}`} tone="aqua" icon={IconCheckCircle}>
              <ProgressBar percent={totals.percent} className="mt-3" />
            </StatCard>
            <StatCard
              label="Behind schedule"
              value={totals.behind}
              hint={totals.behind > 0 ? "employees under 50%" : "everyone is on track"}
              tone={totals.behind > 0 ? "warning" : "success"}
              icon={IconUsers}
            />
          </div>

          {top.length > 0 && (
            <Panel title="Top performers" subtitle="Most bottles marked so far">
              <ol className="grid gap-3 sm:grid-cols-3">
                {top.map((e, i) => (
                  <li key={e.employeeId} className="flex items-center gap-3 rounded-xl bg-surface-subtle p-3.5">
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br text-sm font-extrabold text-white shadow ${MEDAL[i]}`} aria-label={`Rank ${i + 1}`}>
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold text-gray-900">{e.employeeName}</p>
                      <p className="truncate text-xs text-gray-500">{e.regionName ?? e.employeeCode}</p>
                    </div>
                    <p className="text-right text-lg font-extrabold tabular-nums text-heading">
                      {e.bottles}
                      <span className="block text-[10px] font-semibold uppercase tracking-wider text-gray-400">bottles</span>
                    </p>
                  </li>
                ))}
              </ol>
            </Panel>
          )}

          <Panel
            flush
            title={
              <>
                Employees <span className="ml-1 font-medium text-gray-400">{rows.length}</span>
              </>
            }
            action={
              <div className="flex flex-wrap items-center gap-2">
                <FilterChip active={behindOnly} onClick={() => setBehindOnly((v) => !v)} count={totals.behind}>Behind only</FilterChip>
                <SearchBox hotkey value={query} onChange={setQuery} placeholder="Search employee, code or region" className="w-full sm:w-64" />
              </div>
            }
          >
            <div className="flex items-center gap-2 border-b border-surface-border px-4 py-2.5 sm:px-5">
              <span className="text-xs font-semibold text-gray-500">Sort</span>
              <SegmentedControl
                label="Sort employees"
                value={sort}
                onChange={setSort}
                options={[
                  { value: "behind", label: "Behind first" },
                  { value: "bottles", label: "Most bottles" },
                  { value: "name", label: "A–Z" },
                ]}
              />
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
                            <div className="truncate font-semibold text-gray-900">{e.employeeName}</div>
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
                      <td className="px-4 py-3 font-bold tabular-nums" data-label="Bottles">{e.bottles}</td>
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
          </Panel>

          <Panel flush title="Recent submissions" subtitle="Latest entries as they come in">
            {data.recentSubmissions.length === 0 ? (
              <p className="px-5 py-10 text-center text-sm text-gray-500">No submissions yet.</p>
            ) : (
              <ul className="max-h-96 divide-y divide-surface-border overflow-auto">
                {data.recentSubmissions.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 sm:px-5">
                    <Avatar name={s.employeeName ?? "?"} />
                    <div className="min-w-0 flex-1 basis-48">
                      <p className="truncate text-sm font-semibold text-gray-900">
                        {s.storeName} <span className="font-normal text-gray-400">{s.storeCode}</span>
                      </p>
                      <p className="text-xs text-gray-500">
                        {s.employeeName ?? "—"} · for {s.orderDate} · {new Date(s.submittedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        {s.source === "admin" && <span className="ml-2 align-middle"><Badge tone="warning">admin</Badge></span>}
                      </p>
                    </div>
                    <p className="text-lg font-extrabold tabular-nums text-heading">
                      {s.bottleCount}
                      <span className="ml-1 text-xs font-semibold text-gray-400">btl</span>
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
