import { useState } from "react";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useHistory, useOptions, type HistoryItem } from "@/features/zero/api";
import { fmtDay, fmtMoment, fmtShort, monthLabel } from "@/features/zero/parts";
import { ZeroFilters } from "@/features/zero/ZeroFilters";
import { useZeroFilters } from "@/features/zero/useZeroFilters";

const EVENT: Record<string, string> = { reviewed: "Reviewed", verified: "Verified", flagged: "Flagged for correction", month_reopened: "Month reopened", closed_month_verified: "Verified after the month closed" };
const TONE: Record<string, "info" | "success" | "danger" | "warning"> = { reviewed: "info", verified: "success", flagged: "danger", month_reopened: "warning", closed_month_verified: "warning" };
const period = (i: HistoryItem) => (i.period_type === "week" ? `Week ${fmtShort(i.period_start)} – ${fmtShort(i.period_end)}` : monthLabel(i.period_start.slice(0, 7)));

/** Read-only: every review and verification ever made in the caller's scope, newest first. Nothing here can be edited or deleted, not even in the database. */
export function HistoryPanel({ f }: { f: ReturnType<typeof useZeroFilters> }) {
  const opts = useOptions();
  const [reviewer, setReviewer] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const page = Number(f.params.get("page") ?? 1) || 1;
  const q = useHistory(f.values, page, { reviewer, status, from, to });
  const d = q.data;

  return (
    <div className="flex flex-col gap-4">
      <ZeroFilters f={f} options={opts.data} show={{ status: false }} />
      <div className="grid gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Input label="Reviewer (name or ID)" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
        <Select label="Result" value={status} onChange={(e) => setStatus(e.target.value)} options={[{ value: "", label: "Any" }, { value: "reviewed", label: "Reviewed" }, { value: "verified", label: "Verified" }, { value: "flagged", label: "Flagged" }]} />
        <Input label="Period from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <Input label="Period to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>

      {q.isLoading && <Skeleton className="h-64" />}
      {q.isError && <ErrorState message={q.error instanceof Error ? q.error.message : "Couldn't load the log."} onRetry={() => q.refetch()} />}
      {d && (
        <>
          <p className="text-sm text-gray-500">{d.total.toLocaleString()} entr{d.total === 1 ? "y" : "ies"} in the log</p>
          <Table>
            <thead><tr><Th>When</Th><Th>Store</Th><Th>Period</Th><Th>What happened</Th><Th className="text-right">Streak</Th><Th>Reason and remark</Th><Th>By</Th></tr></thead>
            <tbody>
              {d.items.length === 0 && <TableEmpty colSpan={7}>Nothing in the log matches.</TableEmpty>}
              {d.items.map((i) => (
                <tr key={i.id}>
                  <Td className="whitespace-nowrap text-xs">{fmtMoment(i.at)}</Td>
                  <Td>{i.store ? <><span className="font-semibold text-gray-900">{i.store.name}</span><span className="block text-xs text-gray-500">{i.store.outlet_id}</span></> : <span className="text-gray-400">whole month</span>}</Td>
                  <Td className="whitespace-nowrap text-xs">{period(i)}</Td>
                  <Td><Badge tone={TONE[i.event] ?? "neutral"}>{EVENT[i.event] ?? i.event}</Badge>{i.from_status && i.to_status && <span className="block text-[11px] text-gray-500">{i.from_status} → {i.to_status}</span>}</Td>
                  <Td className="text-right tabular-nums text-xs">{i.longest_streak ?? "—"}{i.threshold ? <span className="block text-gray-400">flag at {i.threshold}+</span> : null}</Td>
                  <Td className="max-w-[20rem] text-xs text-gray-700">{i.reason && <b>{i.reason}. </b>}{i.remark}{i.follow_up_date && <span className="block text-gray-400">follow up {fmtDay(i.follow_up_date)}</span>}</Td>
                  <Td className="text-xs">{i.by}<span className="block text-gray-500">{i.by_code}</span></Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={d.page} pageSize={d.page_size} total={d.total} onPageChange={(p) => { const n = new URLSearchParams(f.params); n.set("page", String(p)); f.setParams(n, { replace: true }); }} />
        </>
      )}
    </div>
  );
}
