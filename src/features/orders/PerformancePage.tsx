import { Fragment, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { IconCheckCircle, IconDownload, IconUsers } from "@/components/ui/icons";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { downloadCsv } from "@/lib/csv";
import { usePersistentState } from "@/hooks/usePersistentState";
import { usePartners } from "@/features/stores/useStores";
import { Avatar, FilterChip, Panel, ProgressBar, ProgressRing, SearchBox, SegmentedControl, StatCard } from "@/features/orders/ui";
import { apiRequest } from "@/services/api";

interface Day { date: string; done: number; expected: number; percent: number; cumulative: number }
interface Row {
  employee_id: string; employee_code: string; employee_name: string; region_name: string | null;
  stores: number; expected: number; done: number; missing: number; percent: number; yesterday_percent: number | null; daily: Day[];
}
interface Performance {
  partner_slug: string; partner_label: string; month: string; month_label: string; from: string | null; as_of: string | null; days: number; today: string;
  summary: { employees: number; expected: number; done: number; percent: number; below_50: number };
  employees: Row[];
}

function usePerformance(partner: string, month: string) {
  return useQuery({
    queryKey: ["performance", partner, month],
    queryFn: () => apiRequest<Performance>(`/orders/performance?partner=${encodeURIComponent(partner)}${month ? `&month=${month}` : ""}`),
    enabled: Boolean(partner),
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

const tone = (p: number): "success" | "warning" | "danger" => (p >= 85 ? "success" : p >= 50 ? "warning" : "danger");
const dayChip = (p: number) => (p >= 85 ? "bg-status-success/15 text-status-success" : p >= 50 ? "bg-status-warning-soft text-status-warning" : "bg-status-danger-soft text-status-danger");
const shortDay = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * Performance: for each employee, the share of the entries they should have marked this month (every live store in their scope, every finished day)
 * that they have marked. It is recounted from the entries on every look, from the 1st to yesterday, so days marked late lift the days before them.
 */
export function PerformancePage() {
  const { data: partners = [] } = usePartners();
  const [pickedPartner, setPartner] = usePersistentState<string>("orders.platform", "");
  const [month, setMonth] = useState("");                         // "" = the server's default (the month of yesterday)
  const partner = partners.some((p) => p.slug === pickedPartner) ? pickedPartner : (partners[0]?.slug ?? "");
  const q = usePerformance(partner, month);
  const [query, setQuery] = useState("");
  const [behindOnly, setBehindOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const d = q.data;

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (d?.employees ?? []).filter((e) => (!behindOnly || e.percent < 50) && (!needle || e.employee_name.toLowerCase().includes(needle) || e.employee_code.toLowerCase().includes(needle) || (e.region_name ?? "").toLowerCase().includes(needle)));
  }, [d, query, behindOnly]);

  const current = d?.month ?? month;
  const thisMonth = (() => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`; })();

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl label="Platform" value={partner} onChange={(v) => { setPartner(v); setOpen(null); }} options={partners.map((p) => ({ value: p.slug, label: p.name }))} />
        <div className="ml-auto flex items-center gap-1">
          <Button size="sm" variant="secondary" aria-label="Previous month" disabled={!current} onClick={() => setMonth(shiftMonth(current, -1))}>‹</Button>
          <span className="min-w-[8rem] text-center text-sm font-extrabold text-heading">{d?.month_label ?? "…"}</span>
          <Button size="sm" variant="secondary" aria-label="Next month" disabled={!current || current >= thisMonth} onClick={() => setMonth(shiftMonth(current, 1))}>›</Button>
        </div>
      </div>

      {q.isLoading && <Skeleton className="h-64 !rounded-2xl" />}
      {q.isError && <ErrorState message="Couldn't load the performance." onRetry={() => q.refetch()} />}

      {d && (
        <>
          <section className="relative overflow-hidden rounded-2xl border border-surface-border bg-surface p-4 shadow-card sm:p-6">
            <span aria-hidden="true" className="pointer-events-none absolute -right-12 -top-16 h-52 w-52 rounded-full bg-gradient-to-br from-brand-500/15 to-aqua-400/10 blur-2xl" />
            <div className="relative flex flex-wrap items-center gap-x-8 gap-y-5">
              <ProgressRing percent={d.summary.percent} size={128} sublabel="marked" />
              <div className="min-w-[14rem] flex-1">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-brand-600">{d.partner_label}</p>
                <h3 className="mt-0.5 text-xl font-extrabold text-heading">{d.month_label}</h3>
                <p className="mt-1 text-sm text-gray-500">
                  {d.days === 0
                    ? "No day of this month has finished yet."
                    : <>Counted from {shortDay(d.from!)} to {shortDay(d.as_of!)} ({d.days} day{d.days === 1 ? "" : "s"}). Recounted from the entries every time you open this page, so days an employee marks late raise their earlier days too.</>}
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="secondary" disabled={!rows.length} onClick={() =>
                    downloadCsv(`performance-${d.partner_slug}-${d.month}.csv`,
                      ["Employee code", "Employee", "Region", "Stores", "Should mark", "Marked", "Missing", "Performance %", ...(d.employees[0]?.daily ?? []).map((x) => x.date)],
                      rows.map((e) => [e.employee_code, e.employee_name, e.region_name, e.stores, e.expected, e.done, e.missing, e.percent, ...e.daily.map((x) => x.percent)]))}>
                    <IconDownload className="h-3.5 w-3.5" aria-hidden="true" />
                    Export CSV
                  </Button>
                </div>
              </div>
            </div>
          </section>

          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Entries marked" value={`${d.summary.done.toLocaleString()} / ${d.summary.expected.toLocaleString()}`} tone="aqua" icon={IconCheckCircle}>
              <ProgressBar percent={d.summary.percent} className="mt-3" />
            </StatCard>
            <StatCard label="Team average" value={`${d.summary.percent}%`} tone="brand" icon={IconCheckCircle} />
            <StatCard label="Under 50%" value={d.summary.below_50} hint={d.summary.below_50 > 0 ? "employees behind this month" : "everyone is on track"} tone={d.summary.below_50 > 0 ? "warning" : "success"} icon={IconUsers} />
          </div>

          <Panel
            flush
            title={<>Employees <span className="ml-1 font-medium text-gray-400">{rows.length}</span></>}
            subtitle="Lowest first. Open a row to see every day."
            action={
              <div className="flex flex-wrap items-center gap-2">
                <FilterChip active={behindOnly} onClick={() => setBehindOnly((v) => !v)} count={d.summary.below_50}>Under 50% only</FilterChip>
                <SearchBox hotkey value={query} onChange={setQuery} placeholder="Search employee, code or region" className="w-full sm:w-64" />
              </div>
            }
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-5 py-3">Employee</th><th className="px-4 py-3">Stores</th><th className="px-4 py-3">Marked / should mark</th>
                    <th className="px-4 py-3">Missing</th><th className="w-64 px-4 py-3">Performance</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-12 text-center text-gray-500">No employees match.</td></tr>}
                  {rows.map((e) => (
                    <Fragment key={e.employee_id}>
                      <tr className="cursor-pointer border-b border-surface-border hover:bg-surface-subtle/70" onClick={() => setOpen(open === e.employee_id ? null : e.employee_id)}>
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <Avatar name={e.employee_name} />
                            <div className="min-w-0">
                              <div className="truncate font-semibold text-gray-900">{e.employee_name}</div>
                              <div className="text-xs text-gray-500">{e.employee_code}{e.region_name ? ` · ${e.region_name}` : ""}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 tabular-nums">{e.stores}</td>
                        <td className="px-4 py-3 tabular-nums">{e.done.toLocaleString()} <span className="text-gray-400">/ {e.expected.toLocaleString()}</span></td>
                        <td className="px-4 py-3 font-bold tabular-nums">{e.missing.toLocaleString()}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <ProgressBar percent={e.percent} className="min-w-[6rem] flex-1" />
                            <Badge tone={tone(e.percent)}>{e.percent}%</Badge>
                          </div>
                        </td>
                      </tr>
                      {open === e.employee_id && (
                        <tr className="border-b border-surface-border bg-surface-subtle/50">
                          <td colSpan={5} className="px-5 py-4">
                            <p className="mb-2 text-xs font-semibold text-gray-500">Each day: the share of this employee's stores that have an entry for that day today. The small number is their average from the 1st up to that day.</p>
                            <div className="flex flex-wrap gap-1.5">
                              {e.daily.map((x) => (
                                <span key={x.date} title={`${shortDay(x.date)}: ${x.done} of ${x.expected} stores marked · average so far ${x.cumulative}%`} className={`rounded-lg px-2.5 py-1.5 text-center text-xs font-semibold ${dayChip(x.percent)}`}>
                                  <span className="block text-[10px] opacity-70">{shortDay(x.date)}</span>
                                  {x.percent}%
                                  <span className="block text-[10px] opacity-70">avg {x.cumulative}%</span>
                                </span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
