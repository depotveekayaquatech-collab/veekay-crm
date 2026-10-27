import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { IconDownload } from "@/components/ui/icons";
import { currentMonth, dayLabel, monthRange } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import { pushToast } from "@/lib/toast";
import { downloadCappingSheet, getCappingSheet, type CapRow, type SheetFormat } from "@/services/capping";

const PREVIEW_STORES = 200;       // the file always has every store; the page shows the first rows
const MAX_DAYS = 365;

function span(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000) + 1;
}

/** Download Capping Sheet: pick dates (this month by default) and optionally one store, preview the matrix, download it as CSV or Excel. */
export function CappingSheetTab({ rows: storeRows }: { rows: CapRow[] }) {
  const month = currentMonth();
  const [from, setFrom] = useState(monthRange(month).from);
  const [to, setTo] = useState(monthRange(month).to);
  const [storeId, setStoreId] = useState("");

  const days = from && to ? span(from, to) : 0;
  const problem = !from || !to ? "Choose both dates." : days < 1 ? "The “to” date must not be before the “from” date." : days > MAX_DAYS ? `Choose at most ${MAX_DAYS} days.` : "";
  const options = useMemo(
    () => [...storeRows].sort((a, b) => a.outletName.localeCompare(b.outletName)).map((r) => ({ value: r.storeId, label: `${r.outletName} (${r.outletId})` })),
    [storeRows],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["capping", "sheet", from, to, storeId],
    queryFn: () => getCappingSheet(from, to, storeId || undefined),
    enabled: !problem,
    staleTime: 30_000,
  });
  const download = useMutation({
    mutationFn: (format: SheetFormat) => downloadCappingSheet(from, to, storeId || undefined, format),
    onSuccess: (_d, format) => pushToast(`Capping sheet downloaded (${format === "csv" ? "CSV" : "Excel"}).`, "success"),
  });

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card">
        <div className="grid gap-3 md:grid-cols-[repeat(2,minmax(0,1fr))_minmax(0,2fr)_auto] md:items-end">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            From
            <input className={field} type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            To
            <input className={field} type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Store (optional)
            <Dropdown value={storeId} onValueChange={setStoreId} options={options} placeholder="All stores" searchable aria-label="Store" />
          </label>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => download.mutate("csv")} disabled={!!problem} isLoading={download.isPending && download.variables === "csv"}>
              <IconDownload className="h-4 w-4" /> Download CSV
            </Button>
            <Button onClick={() => download.mutate("xlsx")} disabled={!!problem} isLoading={download.isPending && download.variables === "xlsx"}>
              <IconDownload className="h-4 w-4" /> Download Excel
            </Button>
          </div>
        </div>
        {problem && <p role="alert" className="mt-2 text-sm text-status-danger">{problem}</p>}
      </section>

      {!problem && isLoading && <Skeleton className="h-64" />}
      {!problem && isError && <ErrorState message={error instanceof Error ? error.message : "Couldn't load the capping sheet."} onRetry={() => refetch()} />}
      {!problem && data && data.rows.length === 0 && <EmptyState title="No stores" description="There are no live Zepto stores for this selection." />}
      {!problem && data && data.rows.length > 0 && (
        <>
          <div className="max-h-[70vh] overflow-auto rounded-xl border border-surface-border bg-surface shadow-card" tabIndex={0} aria-label="Capping sheet preview">
            <table className="border-collapse text-sm">
              <thead>
                <tr className="text-[11px] font-bold uppercase tracking-wider text-gray-500">
                  <th className="sticky left-0 top-0 z-30 min-w-[240px] border-b border-r border-surface-border bg-surface-subtle px-3 py-2.5 text-left">Store</th>
                  {data.dates.map((d) => (
                    <th key={d} className="sticky top-0 z-20 min-w-[56px] border-b border-surface-border bg-surface-subtle px-2 py-2.5 text-center">{dayLabel(d)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.slice(0, PREVIEW_STORES).map((r) => (
                  <tr key={r.storeId} className="border-b border-surface-border/60 hover:bg-surface-subtle/50">
                    <td className="sticky left-0 z-10 max-w-[280px] border-r border-surface-border bg-surface px-3 py-2">
                      <p className="truncate font-semibold text-gray-900" title={r.outletName}>{r.outletName}</p>
                      <p className="truncate text-[11px] text-gray-500">{r.outletId}</p>
                    </td>
                    {r.cells.map((c, i) => {
                      const changed = i > 0 && c !== r.cells[i - 1];       // the day the capping changed
                      return (
                        <td key={data.dates[i]} className={`px-2 py-2 text-center tabular-nums ${changed ? "bg-brand-500/10 font-bold text-brand-700" : "text-gray-700"}`} title={changed ? "Capping changed this day" : undefined}>
                          {c ?? <span className="text-gray-300">—</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-500">
            {data.rows.length > PREVIEW_STORES ? `Showing the first ${PREVIEW_STORES} of ${data.rows.length} stores. The download has all of them. ` : `${data.rows.length} store${data.rows.length === 1 ? "" : "s"}. `}
            A dash means no capping had been set yet. Highlighted cells are the day the capping changed.
          </p>
        </>
      )}
    </div>
  );
}
