import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useMonthly, useOptions, useReopenMonth, useVerifyMonth, type Progress, type ZeroRow } from "@/features/zero/api";
import { Employees, ROW_TONE, StateBadge, StreakCell, fmtDay, fmtMoment, monthLabel } from "@/features/zero/parts";
import { StoreDrawer } from "@/features/zero/StoreDrawer";
import { ZeroFilters } from "@/features/zero/ZeroFilters";
import { monthEnd, shiftMonth, todayIST, useZeroFilters } from "@/features/zero/useZeroFilters";

function Bars({ title, items }: { title: string; items: Progress[] }) {
  if (items.length === 0) return null;
  return (
    <details className="rounded-2xl border border-surface-border bg-surface px-4 py-3">
      <summary className="cursor-pointer text-sm font-bold text-heading">{title}</summary>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {items.map((p) => (
          <li key={p.name} className="rounded-lg bg-surface-subtle px-3 py-2">
            <div className="flex items-center justify-between text-sm"><span className="truncate font-medium text-gray-900">{p.name}</span><span className="text-xs tabular-nums text-gray-600">{p.verified}/{p.total}{p.flagged ? ` · ${p.flagged} flagged` : ""}</span></div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-muted"><div className="h-full rounded-full bg-status-success" style={{ width: `${p.total ? (p.verified / p.total) * 100 : 0}%` }} /></div>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Remark for verifying (or flagging) stores of a month, or the reason for reopening a closed one. */
function RemarkModal({ title, description, confirm, tone, busy, error, onConfirm, onClose }: {
  title: string; description: string; confirm: string; tone?: "danger"; busy: boolean; error: string | null; onConfirm: (remark: string) => void; onClose: () => void;
}) {
  const [remark, setRemark] = useState("");
  return (
    <Modal open onClose={() => !busy && onClose()} title={title} description={description}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button><Button variant={tone === "danger" ? "danger" : "primary"} onClick={() => onConfirm(remark.trim())} isLoading={busy} disabled={remark.trim().length < 3}>{confirm}</Button></>}>
      <div className="flex flex-col gap-3">
        <Input label="Remark (required)" value={remark} onChange={(e) => setRemark(e.target.value)} maxLength={1000} autoFocus />
        {error && <p className="text-sm text-status-danger" role="alert">{error}</p>}
      </div>
    </Modal>
  );
}

/** Verifying the previous month: the full month plus a few days of grace, per store, with progress per region and per employee. */
export function MonthlyPanel({ f }: { f: ReturnType<typeof useZeroFilters> }) {
  const opts = useOptions();
  const month = f.params.get("month") ?? opts.data?.previous_month?.slice(0, 7) ?? "";
  const q = useMonthly(f.values, month, Boolean(month));
  const verify = useVerifyMonth();
  const reopen = useReopenMonth();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [action, setAction] = useState<"verified" | "flagged" | "reopen" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const d = q.data;
  const rows = d?.items ?? [];
  const p = d?.period;
  const setMonth = (m: string) => { const n = new URLSearchParams(f.params); n.set("month", m); n.delete("page"); f.setParams(n, { replace: true }); setPicked(new Set()); };
  const thisMonth = todayIST().slice(0, 7);
  const lastMonth = shiftMonth(thisMonth, -1);
  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const canAct = Boolean(d?.can_review) && Boolean(p?.open || d?.is_admin);
  const waiting = rows.filter((r: ZeroRow) => r.status !== "verified").map((r) => r.store.id);

  function done() { setAction(null); setPicked(new Set()); setError(null); }
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : "Couldn't save.");

  return (
    <div className="flex flex-col gap-4">
      <ZeroFilters f={f} options={opts.data} show={{ status: true }} />

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-surface-border bg-surface p-4">
        <div className="flex items-center gap-1">
          <Button size="sm" variant="secondary" aria-label="Previous month" disabled={!month} onClick={() => setMonth(shiftMonth(month, -1))}>‹</Button>
          <span className="min-w-[10rem] text-center text-base font-extrabold text-heading">{month ? monthLabel(month) : "…"}</span>
          <Button size="sm" variant="secondary" aria-label="Next month" disabled={!month || month >= thisMonth} onClick={() => setMonth(shiftMonth(month, 1))}>›</Button>
        </div>
        <Button size="sm" variant={month === lastMonth ? "primary" : "secondary"} onClick={() => setMonth(lastMonth)}>Last Month</Button>
        {month !== thisMonth && <Button size="sm" variant="ghost" onClick={() => setMonth(thisMonth)}>This Month</Button>}
        {p && (
          <div className={`ml-auto rounded-xl px-3 py-2 text-xs ${p.open ? "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300" : "bg-surface-muted text-gray-600"}`} role="status">
            <b>Verification period:</b> {monthLabel(p.month)} is {p.open ? "open" : "closed"}
            {p.open && p.days_left !== null && <> · {p.days_left} day{p.days_left === 1 ? "" : "s"} left (until {fmtDay(p.closes_on)})</>}
            {p.reopened && <> · reopened by an administrator</>}
            {!p.open && <> · closed on {fmtDay(p.closes_on)}</>}
          </div>
        )}
        {p && !p.open && d?.can_reopen && <Button size="sm" variant="secondary" onClick={() => { setError(null); setAction("reopen"); }}>Reopen month…</Button>}
      </div>

      {q.isLoading && <Skeleton className="h-64" />}
      {q.isError && <ErrorState message={q.error instanceof Error ? q.error.message : "Couldn't load the month."} onRetry={() => q.refetch()} />}
      {d && (
        <>
          <div className="rounded-2xl border border-surface-border bg-surface px-4 py-3">
            <div className="flex items-center justify-between text-sm"><b className="text-heading">{d.progress.overall.verified} of {d.progress.overall.total} stores verified</b><span className="text-xs text-gray-500">{d.progress.overall.flagged} flagged for correction</span></div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-muted"><div className="h-full rounded-full bg-status-success" style={{ width: `${d.progress.overall.total ? (d.progress.overall.verified / d.progress.overall.total) * 100 : 0}%` }} /></div>
          </div>
          <div className="grid gap-3 lg:grid-cols-2"><Bars title="Progress by region" items={d.progress.by_region} /><Bars title="Progress by employee" items={d.progress.by_employee} /></div>

          {canAct && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="secondary" disabled={waiting.length === 0} onClick={() => setPicked(new Set(waiting))}>Select all not verified ({waiting.length})</Button>
              <Button size="sm" disabled={picked.size === 0} onClick={() => { setError(null); setAction("verified"); }}>Verify {picked.size || ""} store{picked.size === 1 ? "" : "s"}…</Button>
              <Button size="sm" variant="secondary" disabled={picked.size === 0} onClick={() => { setError(null); setAction("flagged"); }}>Flag for correction…</Button>
              {picked.size > 0 && <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Clear</Button>}
              {!p?.open && <span className="text-xs text-gray-500">This month is closed: your change is logged as made after closing.</span>}
            </div>
          )}

          <Table>
            <thead>
              <tr>
                {canAct && <Th className="w-8"><span className="sr-only">Select</span></Th>}
                <Th>Store</Th><Th>Assigned to</Th><Th className="text-right">Total orders</Th><Th className="text-right">Zero days</Th><Th className="text-right">Unmarked</Th>
                <Th>Longest streak</Th><Th>Weekly reviews</Th><Th>Verification</Th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && <TableEmpty colSpan={canAct ? 9 : 8}>No stores match these filters.</TableEmpty>}
              {rows.map((r) => (
                <tr key={r.store.id} className={`${ROW_TONE[r.severity]} hover:bg-surface-subtle/70`}>
                  {canAct && <Td><input type="checkbox" aria-label={`Select ${r.store.name}`} checked={picked.has(r.store.id)} onChange={() => toggle(r.store.id)} className="h-4 w-4 rounded border-surface-border text-brand-500" /></Td>}
                  <Td>
                    <button type="button" className="text-left font-semibold text-gray-900 hover:text-brand-600 hover:underline" onClick={() => setOpen(r.store.id)}>{r.store.name}</button>
                    <span className="block text-xs text-gray-500">{r.store.outlet_id}{r.store.region ? ` · ${r.store.region}` : ""}</span>
                  </Td>
                  <Td className="max-w-[12rem] text-sm"><Employees people={r.employees} /></Td>
                  <Td className="text-right font-bold tabular-nums">{r.total_orders.toLocaleString()}</Td>
                  <Td className="text-right tabular-nums">{r.total_zero}</Td>
                  <Td className="text-right tabular-nums">{r.unmarked ? <b className="text-status-warning">{r.unmarked}</b> : 0}</Td>
                  <Td><StreakCell streak={r.longest} severity={r.severity} /></Td>
                  <Td className="text-xs text-gray-600">{Object.keys(r.weekly ?? {}).length === 0 ? <span className="text-gray-400">none</span> : Object.entries(r.weekly ?? {}).map(([k, n]) => `${n} ${k}`).join(", ")}</Td>
                  <Td className="max-w-[14rem]">
                    <StateBadge state={r.status} />
                    {r.review && r.status !== "pending" && <p className="mt-1 text-xs text-gray-600">{r.review.remark}<span className="block text-gray-400">{r.review.by} · {fmtMoment(r.review.at)}</span></p>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}

      {(action === "verified" || action === "flagged") && (
        <RemarkModal title={action === "verified" ? `Verify ${picked.size} store${picked.size === 1 ? "" : "s"}` : `Flag ${picked.size} store${picked.size === 1 ? "" : "s"} for correction`}
          description={`${monthLabel(month)}. Saved in the log with your name and the time.`} confirm={action === "verified" ? "Verify" : "Flag"} tone={action === "flagged" ? "danger" : undefined}
          busy={verify.isPending} error={error} onClose={() => setAction(null)}
          onConfirm={(remark) => verify.mutate({ month, store_ids: [...picked], status: action, remark }, { onSuccess: done, onError: fail })} />
      )}
      {action === "reopen" && (
        <RemarkModal title={`Reopen ${month ? monthLabel(month) : "the month"}`} description={`Others can verify it again for a few days. Your reason is logged.`} confirm="Reopen"
          busy={reopen.isPending} error={error} onClose={() => setAction(null)}
          onConfirm={(reason) => reopen.mutate({ month, reason }, { onSuccess: done, onError: fail })} />
      )}
      {open && <StoreDrawer storeId={open} filters={{ ...f.values, from: `${month}-01`, to: monthEnd(month) }} onClose={() => setOpen(null)} />}
    </div>
  );
}
