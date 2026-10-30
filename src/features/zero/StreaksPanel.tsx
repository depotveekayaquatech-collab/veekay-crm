import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconDownload } from "@/components/ui/icons";
import { pushToast } from "@/lib/toast";
import { downloadExport, useOptions, useStreaks } from "@/features/zero/api";
import { Employees, ROW_TONE, StateBadge, StreakCell, fmtDay, fmtMoment } from "@/features/zero/parts";
import { StoreDrawer } from "@/features/zero/StoreDrawer";
import { ZeroFilters } from "@/features/zero/ZeroFilters";
import { useZeroFilters } from "@/features/zero/useZeroFilters";

const Tile = ({ label, value, tone = "text-heading" }: { label: string; value: number; tone?: string }) => (
  <div className="rounded-xl border border-surface-border bg-surface px-4 py-3">
    <p className="text-[11px] font-bold text-gray-400">{label}</p>
    <p className={`text-xl font-extrabold tabular-nums ${tone}`}>{value.toLocaleString()}</p>
  </div>
);

/** Stores with a run of N or more zero days in the chosen range, plus the stores nobody reported on. */
export function StreaksPanel({ f }: { f: ReturnType<typeof useZeroFilters> }) {
  const opts = useOptions();
  const page = Number(f.params.get("page") ?? 1) || 1;
  const q = useStreaks(f.values, page);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const d = q.data;

  async function exportCsv() {
    setBusy(true);
    try { await downloadExport(f.values); } catch (e) { pushToast(e instanceof Error ? e.message : "Couldn't export.", "error"); } finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-4">
      <ZeroFilters f={f} options={opts.data} show={{ dates: true, streak: true, status: true }}
        actions={<Button type="button" variant="secondary" isLoading={busy} onClick={exportCsv} disabled={!d?.total}><IconDownload className="h-4 w-4" aria-hidden="true" /> Export CSV</Button>} />

      {q.isLoading && <Skeleton className="h-64" />}
      {q.isError && <ErrorState message={q.error instanceof Error ? q.error.message : "Couldn't load the report."} onRetry={() => q.refetch()} />}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Tile label="Stores shown" value={d.summary.stores} />
            <Tile label="With a zero streak" value={d.summary.with_zero_streak} tone={d.summary.with_zero_streak ? "text-status-warning" : undefined} />
            <Tile label="Streak ongoing" value={d.summary.ongoing} tone={d.summary.ongoing ? "text-status-danger" : undefined} />
            <Tile label="With unmarked days" value={d.summary.with_unmarked} />
            <Tile label="Not reviewed yet" value={d.summary.pending} />
          </div>
          <p className="text-xs text-gray-500">
            {fmtDay(d.range.from)} to {fmtDay(d.range.to)}. A zero is a day somebody entered 0; a day with no entry is “unmarked”. Today and company holidays are not counted. Click a store for its days.
          </p>
          <Table>
            <thead>
              <tr>
                <Th>Store</Th><Th>Assigned to</Th><Th>Longest zero streak</Th><Th className="text-right">Zero days</Th><Th className="text-right">Unmarked</Th>
                <Th>Last orders</Th><Th>Zeros marked by</Th><Th>Review</Th>
              </tr>
            </thead>
            <tbody>
              {d.items.length === 0 && <TableEmpty colSpan={8}>No stores match these filters.</TableEmpty>}
              {d.items.map((r) => (
                <tr key={r.store.id} tabIndex={0} onClick={() => setOpen(r.store.id)} onKeyDown={(e) => e.key === "Enter" && setOpen(r.store.id)}
                  className={`cursor-pointer hover:bg-surface-subtle/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 ${ROW_TONE[r.severity]}`}>
                  <Td>
                    <span className="font-semibold text-gray-900">{r.store.name}</span>
                    <span className="block text-xs text-gray-500">{r.store.outlet_id}{r.store.region ? ` · ${r.store.region}` : ""}{r.store.platform ? ` · ${r.store.platform}` : ""}</span>
                  </Td>
                  <Td className="max-w-[12rem] text-sm"><Employees people={r.employees} /></Td>
                  <Td><StreakCell streak={r.longest} severity={r.severity} /></Td>
                  <Td className="text-right tabular-nums">{r.total_zero}</Td>
                  <Td className="text-right tabular-nums">{r.unmarked ? <b className="text-status-warning">{r.unmarked}</b> : 0}</Td>
                  <Td className="whitespace-nowrap text-xs">{fmtDay(r.last_nonzero)}</Td>
                  <Td className="text-xs">{r.marked_by ? <>{r.marked_by.name ?? "unknown"}<span className="block text-gray-500">{fmtMoment(r.marked_by.at)}</span></> : <span className="text-gray-400">—</span>}</Td>
                  <Td><StateBadge state={r.status} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={d.page} pageSize={d.page_size} total={d.total} onPageChange={(p) => { const n = new URLSearchParams(f.params); n.set("page", String(p)); f.setParams(n, { replace: true }); }} />
        </>
      )}
      {open && <StoreDrawer storeId={open} filters={f.values} onClose={() => setOpen(null)} />}
    </div>
  );
}
