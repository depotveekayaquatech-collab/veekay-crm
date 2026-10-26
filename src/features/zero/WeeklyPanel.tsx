import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/Badge";
import { useOptions, useReviewWeek, useWeekly, type ZeroRow } from "@/features/zero/api";
import { Employees, ROW_TONE, StateBadge, StreakCell, fmtDay, fmtMoment, fmtShort } from "@/features/zero/parts";
import { StoreDrawer } from "@/features/zero/StoreDrawer";
import { ZeroFilters } from "@/features/zero/ZeroFilters";
import { addDays, useZeroFilters } from "@/features/zero/useZeroFilters";

/** Reason + remark (+ optional follow-up date) for one store or many at once. The server keeps every version in the log. */
function ReviewModal({ rows, week, threshold, onClose }: { rows: ZeroRow[]; week: string; threshold: number; onClose: () => void }) {
  const opts = useOptions();
  const review = useReviewWeek();
  const [reason, setReason] = useState("");
  const [remark, setRemark] = useState("");
  const [follow, setFollow] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ok = reason && remark.trim().length >= 3;

  function submit() {
    setError(null);
    review.mutate({ week_start: week, store_ids: rows.map((r) => r.store.id), threshold, reason, remark: remark.trim(), follow_up_date: follow },
      { onSuccess: onClose, onError: (e) => setError(e instanceof Error ? e.message : "Couldn't save.") });
  }

  return (
    <Modal open onClose={() => !review.isPending && onClose()} title={rows.length === 1 ? `Review ${rows[0].store.name}` : `Review ${rows.length} stores`}
      description={`Week of ${fmtShort(week)} to ${fmtShort(addDays(week, 5))} · flagged at ${threshold}+ zero days in a row`}
      footer={<><Button variant="secondary" onClick={onClose} disabled={review.isPending}>Cancel</Button><Button onClick={submit} isLoading={review.isPending} disabled={!ok}>Mark reviewed</Button></>}>
      <div className="flex flex-col gap-4">
        <Select label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Choose a reason" options={(opts.data?.reasons ?? []).map((r) => ({ value: r.value, label: r.label }))} />
        <Input label="Remark (required)" value={remark} onChange={(e) => setRemark(e.target.value)} maxLength={1000} placeholder="What did you find out?" />
        <Input label="Follow-up date (optional)" type="date" value={follow} min={new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" })} onChange={(e) => setFollow(e.target.value)} />
        {rows.length > 1 && <p className="text-xs text-gray-500">The same reason and remark are saved for all {rows.length} stores, each as its own entry in the log.</p>}
        {error && <p className="text-sm text-status-danger" role="alert">{error}</p>}
      </div>
    </Modal>
  );
}

/** The Saturday review: the stores that sat at zero for the threshold or longer this week, who marked them, and a decision on each. */
export function WeeklyPanel({ f }: { f: ReturnType<typeof useZeroFilters> }) {
  const opts = useOptions();
  const week = f.params.get("week") ?? opts.data?.default_week ?? "";
  const threshold = Number(f.params.get("thr") ?? opts.data?.weekly_threshold ?? 3) || 3;
  const q = useWeekly(f.values, week, threshold, Boolean(week));
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [reviewing, setReviewing] = useState<ZeroRow[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const d = q.data;
  const rows = d?.items ?? [];
  const canReview = Boolean(d?.can_review);
  const toReview = useMemo(() => rows.filter((r) => picked.has(r.store.id)), [rows, picked]);
  const setWeek = (w: string) => { const n = new URLSearchParams(f.params); n.set("week", w); n.delete("page"); f.setParams(n, { replace: true }); setPicked(new Set()); };
  const setThr = (t: string) => { const n = new URLSearchParams(f.params); n.set("thr", t); f.setParams(n, { replace: true }); };
  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const pendingIds = rows.filter((r) => r.status === "pending").map((r) => r.store.id);

  return (
    <div className="flex flex-col gap-4">
      <ZeroFilters f={f} options={opts.data} show={{ status: true }} />

      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-surface-border bg-surface p-4">
        <div className="flex items-center gap-1">
          <Button size="sm" variant="secondary" aria-label="Previous week" disabled={!week} onClick={() => setWeek(addDays(week, -7))}>‹</Button>
          <div className="min-w-[13rem] text-center">
            <p className="text-sm font-extrabold text-heading">{week ? `${fmtShort(week)} – ${fmtShort(addDays(week, 5))}` : "…"}</p>
            <p className="text-[11px] text-gray-500">Monday to Saturday{d?.is_current_default ? " · latest review cycle" : ""}</p>
          </div>
          <Button size="sm" variant="secondary" aria-label="Next week" disabled={!week || addDays(week, 7) > (d?.today ?? "")} onClick={() => setWeek(addDays(week, 7))}>›</Button>
          {opts.data && week !== opts.data.default_week && <Button size="sm" variant="ghost" onClick={() => setWeek(opts.data!.default_week)}>Latest</Button>}
        </div>
        <div className="w-56">
          <Select label="Flag stores with zero days in a row" value={String(threshold)} onChange={(e) => setThr(e.target.value)} options={[1, 2, 3, 4, 5, 6].map((n) => ({ value: String(n), label: `${n} or more` }))} />
        </div>
      </div>

      {q.isLoading && <Skeleton className="h-64" />}
      {q.isError && <ErrorState message={q.error instanceof Error ? q.error.message : "Couldn't load the week."} onRetry={() => q.refetch()} />}
      {d && (
        <>
          <div role="status" className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border px-4 py-3 ${d.summary.complete ? "border-emerald-500/30 bg-emerald-500/10" : "border-amber-500/30 bg-amber-500/10"}`}>
            <p className="text-sm font-bold text-heading">
              {d.summary.flagged} flagged store{d.summary.flagged === 1 ? "" : "s"}, {d.summary.reviewed} reviewed, {d.summary.pending} pending
            </p>
            <Badge tone={d.summary.complete ? "success" : "warning"} dot>{d.summary.complete ? "Week complete" : "Week not complete"}</Badge>
          </div>

          {d.markers.length > 0 && (
            <details className="rounded-2xl border border-surface-border bg-surface px-4 py-3" open={d.markers[0].stores >= 3}>
              <summary className="cursor-pointer text-sm font-bold text-heading">Who marked these zeros</summary>
              <p className="mt-1 text-xs text-gray-500">One person marking zeros in many stores is worth a conversation.</p>
              <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {d.markers.map((m) => (
                  <li key={m.name} className="flex items-center justify-between rounded-lg bg-surface-subtle px-3 py-1.5 text-sm">
                    <span className="font-medium text-gray-900">{m.name}</span>
                    <span className="text-xs text-gray-600">{m.stores} store{m.stores === 1 ? "" : "s"} · {m.zero_days} zero day{m.zero_days === 1 ? "" : "s"}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {canReview && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="secondary" disabled={pendingIds.length === 0} onClick={() => setPicked(new Set(pendingIds))}>Select all pending ({pendingIds.length})</Button>
              <Button size="sm" disabled={picked.size === 0} onClick={() => setReviewing(toReview)}>Mark {picked.size || ""} reviewed…</Button>
              {picked.size > 0 && <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Clear</Button>}
            </div>
          )}

          <Table>
            <thead>
              <tr>
                {canReview && <Th className="w-8"><span className="sr-only">Select</span></Th>}
                <Th>Store</Th><Th>Assigned to</Th><Th>Zero streak</Th><Th className="text-right">Unmarked</Th><Th>Zeros marked by</Th><Th>Review</Th>{canReview && <Th className="text-right">Action</Th>}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && <TableEmpty colSpan={canReview ? 8 : 6}>No store was at zero for {threshold} or more days in a row this week.</TableEmpty>}
              {rows.map((r) => (
                <tr key={r.store.id} className={`${ROW_TONE[r.severity]} hover:bg-surface-subtle/70`}>
                  {canReview && <Td><input type="checkbox" aria-label={`Select ${r.store.name}`} checked={picked.has(r.store.id)} onChange={() => toggle(r.store.id)} className="h-4 w-4 rounded border-surface-border text-brand-500" /></Td>}
                  <Td>
                    <button type="button" className="text-left font-semibold text-gray-900 hover:text-brand-600 hover:underline" onClick={() => setOpen(r.store.id)}>{r.store.name}</button>
                    <span className="block text-xs text-gray-500">{r.store.outlet_id}{r.store.region ? ` · ${r.store.region}` : ""}</span>
                  </Td>
                  <Td className="max-w-[12rem] text-sm"><Employees people={r.employees} /></Td>
                  <Td><StreakCell streak={r.longest} severity={r.severity} /></Td>
                  <Td className="text-right tabular-nums">{r.unmarked}</Td>
                  <Td className="text-xs">{r.marked_by ? <>{r.marked_by.name ?? "unknown"}<span className="block text-gray-500">{fmtMoment(r.marked_by.at)}</span></> : "—"}</Td>
                  <Td className="max-w-[16rem]">
                    <StateBadge state={r.status} />
                    {r.review && r.status !== "pending" && (
                      <p className="mt-1 text-xs text-gray-600">
                        {r.review.remark}
                        <span className="block text-gray-400">{r.review.by} · {fmtMoment(r.review.at)}{r.review.follow_up_date ? ` · follow up ${fmtDay(r.review.follow_up_date)}` : ""}</span>
                      </p>
                    )}
                  </Td>
                  {canReview && <Td className="text-right"><Button size="sm" variant={r.status === "pending" ? "primary" : "secondary"} onClick={() => setReviewing([r])}>{r.status === "pending" ? "Review" : "Review again"}</Button></Td>}
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
      {reviewing && <ReviewModal rows={reviewing} week={week} threshold={threshold} onClose={() => { setReviewing(null); setPicked(new Set()); }} />}
      {open && <StoreDrawer storeId={open} filters={{ ...f.values, from: week, to: addDays(week, 5), n: threshold }} onClose={() => setOpen(null)} />}
    </div>
  );
}
