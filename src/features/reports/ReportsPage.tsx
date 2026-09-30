import { useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Table, Td, Th, TableEmpty } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { AreaChart } from "@/features/dashboard/charts";
import { IconDownload } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { daysAgo, isoDate as iso } from "@/lib/dates";
import { useReport } from "@/services/reports";
import type { ReportGroup } from "@/types/report";

const GROUPS: { value: ReportGroup; label: string }[] = [
  { value: "region", label: "Region" },
  { value: "partner", label: "Platform" },
  { value: "state", label: "State" },
  { value: "store", label: "Store" },
];

const PRESETS: { label: string; range: () => [string, string] }[] = [
  { label: "Last 7 days", range: () => [daysAgo(6), iso(new Date())] },
  { label: "Last 30 days", range: () => [daysAgo(29), iso(new Date())] },
  {
    label: "This month",
    range: () => {
      const n = new Date();
      return [iso(new Date(n.getFullYear(), n.getMonth(), 1)), iso(n)];
    },
  },
  {
    label: "Last month",
    range: () => {
      const n = new Date();
      return [iso(new Date(n.getFullYear(), n.getMonth() - 1, 1)), iso(new Date(n.getFullYear(), n.getMonth(), 0))];
    },
  },
];

const dateInput =
  "h-10 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

export function ReportsPage() {
  const [[start, end], setRange] = useState<[string, string]>(PRESETS[1].range);
  const [groupBy, setGroupBy] = useState<ReportGroup>("region");
  const { data, isLoading, isError, refetch } = useReport(start, end, groupBy);

  const top = useMemo(() => data?.rows[0], [data]);
  const invalid = start > end;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Reports"
        subtitle="Bottle volumes over any period, broken down by region, platform, state or store."
        action={
          <Button
            variant="secondary"
            disabled={!data?.rows.length}
            onClick={() =>
              data &&
              downloadCsv(
                `report-${data.groupBy}-${data.start}_${data.end}.csv`,
                [GROUPS.find((g) => g.value === data.groupBy)?.label ?? "Group", "Code", "Bottles", "Share %", "Entries", "Active days", "Avg per entry"],
                data.rows.map((r) => [r.label, r.sub, r.bottles, r.sharePercent, r.entries, r.activeDays, r.avgPerEntry]),
              )
            }
          >
            <IconDownload className="h-4 w-4" />
            Export CSV
          </Button>
        }
      />

      {/* controls */}
      <div className="flex flex-wrap items-end gap-x-6 gap-y-4 rounded-xl border border-surface-border bg-white p-4 shadow-card">
        <div>
          <p className="mb-1.5 text-[13px] font-semibold text-gray-700">Period</p>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => {
              const [s, e] = p.range();
              const active = s === start && e === end;
              return (
                <button
                  key={p.label}
                  onClick={() => setRange([s, e])}
                  className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    active ? "bg-brand-500 text-white shadow-sm" : "bg-surface-subtle text-gray-600 hover:bg-surface-muted"
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            From
            <input type="date" value={start} max={end} onChange={(e) => setRange([e.target.value, end])} className={dateInput} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            To
            <input type="date" value={end} min={start} onChange={(e) => setRange([start, e.target.value])} className={dateInput} />
          </label>
        </div>
        <div>
          <p className="mb-1.5 text-[13px] font-semibold text-gray-700">Group by</p>
          <div className="flex gap-1 rounded-lg bg-surface-subtle p-1">
            {GROUPS.map((g) => (
              <button
                key={g.value}
                onClick={() => setGroupBy(g.value)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                  groupBy === g.value ? "bg-white text-brand-700 shadow-sm" : "text-gray-500 hover:text-gray-800"
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {invalid && <p className="text-sm text-status-danger">“From” must not be after “To”.</p>}
      {isLoading && <Skeleton className="h-72" />}
      {isError && <ErrorState message="Couldn't load the report." onRetry={() => refetch()} />}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Total bottles", value: data.totalBottles.toLocaleString() },
              { label: "Entries", value: data.totalEntries.toLocaleString() },
              { label: "Avg bottles / day", value: data.avgBottlesPerDay.toLocaleString() },
              { label: "Top performer", value: top ? top.label : "—", small: true, hint: top ? `${top.sharePercent}% of volume` : undefined },
            ].map((k, i) => (
              <div key={k.label} className={`tile tile-${["brand", "aqua", "success", "warning"][i]} rounded-xl border border-surface-border bg-white p-5 shadow-card`}>
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{k.label}</p>
                <p className={`mt-1.5 truncate font-bold tabular-nums text-ink-900 ${k.small ? "text-xl leading-9" : "text-[1.7rem] leading-none"}`}>
                  {k.value}
                </p>
                {k.hint && <p className="mt-1 text-xs text-gray-500">{k.hint}</p>}
              </div>
            ))}
          </div>

          <section className="rounded-xl border border-surface-border bg-white shadow-card">
            <header className="border-b border-surface-border/80 px-5 py-4">
              <h3 className="text-sm font-bold text-gray-900">
                Bottles per day · {data.start} → {data.end}
              </h3>
            </header>
            <div className="p-5">
              <AreaChart data={data.series.map((p) => ({ label: p.label, value: p.bottles }))} valueSuffix=" bottles" />
            </div>
          </section>

          <Table>
            <thead>
              <tr>
                <Th>{GROUPS.find((g) => g.value === data.groupBy)?.label}</Th>
                <Th className="text-right">Bottles</Th>
                <Th className="w-56">Share</Th>
                <Th className="text-right">Entries</Th>
                <Th className="text-right">Active days</Th>
                <Th className="text-right">Avg / entry</Th>
              </tr>
            </thead>
            <tbody>
              {data.rows.length === 0 && <TableEmpty colSpan={6}>No entries in this period.</TableEmpty>}
              {data.rows.map((r) => (
                <tr key={r.key}>
                  <Td className="font-medium text-gray-900">
                    {r.label}
                    {r.sub && <span className="ml-2 text-xs font-normal text-gray-400">{r.sub}</span>}
                  </Td>
                  <Td className="text-right font-semibold tabular-nums text-gray-900">{r.bottles.toLocaleString()}</Td>
                  <Td>
                    <div className="flex items-center gap-3">
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted">
                        <div className="h-full rounded-full bg-brand-500" style={{ width: `${r.sharePercent}%` }} />
                      </div>
                      <span className="w-12 text-right text-xs tabular-nums text-gray-500">{r.sharePercent}%</span>
                    </div>
                  </Td>
                  <Td className="text-right tabular-nums">{r.entries}</Td>
                  <Td className="text-right tabular-nums">{r.activeDays}</Td>
                  <Td className="text-right tabular-nums">{r.avgPerEntry}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
    </div>
  );
}
