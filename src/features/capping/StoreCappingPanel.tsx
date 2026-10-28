import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { dateLabel, isBackdated, istToday } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import { pushToast } from "@/lib/toast";
import { changeCapping, changeCappingDate, getCappingHistory, type CapHistoryRow, type CapRow } from "@/services/capping";

const MAX = 1_000_000;
const EARLIEST = "2024-01-01";

/** Move one capping change to another start date: the capping stays, only the day it starts on moves. */
function EditDate({ row, label = "Change date" }: { row: Pick<CapHistoryRow, "id" | "capping" | "effectiveFrom">; label?: string }) {
  const qc = useQueryClient();
  const today = istToday();
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(row.effectiveFrom);
  const bad = !date || date > today || date < EARLIEST;
  const save = useMutation({
    mutationFn: () => changeCappingDate(row.id, date),
    onSuccess: (r) => {
      pushToast(`Capping ${r.capping} now starts on ${dateLabel(r.effectiveFrom)} (was ${dateLabel(r.was)}).`, "success");
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ["capping"] });
    },
  });
  return (
    <>
      <button type="button" onClick={() => { setDate(row.effectiveFrom); setOpen(true); }} className="text-xs font-semibold text-brand-600 hover:text-brand-700">{label}</button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Change the start date"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={() => save.mutate()} isLoading={save.isPending} disabled={bad || date === row.effectiveFrom}>Save date</Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          The capping of <b>{row.capping}</b> a day currently starts on <b>{dateLabel(row.effectiveFrom)}</b>. Choose the day it really started.
        </p>
        <label className="mt-3 flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Starts on
          <input className={field} type="date" value={date} min={EARLIEST} max={today} onChange={(e) => setDate(e.target.value)} aria-invalid={bad} />
        </label>
        {bad && <p role="alert" className="mt-2 text-sm text-status-danger">Choose today or an earlier date.</p>}
      </Modal>
    </>
  );
}

/** The store's record: every capping it has had, with the date it started and who set it, newest first. */
function History({ storeId, canChange }: { storeId: string; canChange: boolean }) {
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ["capping", "history", storeId], queryFn: () => getCappingHistory(storeId), staleTime: 15_000 });
  if (isLoading) return <Skeleton className="h-32" />;
  if (isError) return <ErrorState message={error instanceof Error ? error.message : "Couldn't load the history."} onRetry={() => refetch()} />;
  if (!data) return null;
  if (data.rows.length === 0) return <EmptyState title="No changes recorded yet" description="Once a capping is set for this store, each change appears here with the date it started." />;
  const inForce = data.rows.find((r) => r.effectiveFrom <= data.today)?.id;     // rows are newest first
  return (
    <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface">
      <table className="w-full min-w-[480px] border-collapse text-sm">
        <thead>
          <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
            {["Capping", "Starts", "Set by", ""].map((h, i) => <th key={i} className="border-b border-surface-border px-3 py-2.5 first:pl-4">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-border/60">
              <td className="px-3 py-2.5 pl-4 font-semibold tabular-nums">{r.capping} {r.id === inForce && <Badge tone="success">In force</Badge>}</td>
              <td className="px-3 py-2.5 tabular-nums">{dateLabel(r.effectiveFrom)}</td>
              <td className="px-3 py-2.5 text-gray-700">{r.changedBy ?? "—"}{r.changedByCode ? <span className="text-xs text-gray-500"> ({r.changedByCode})</span> : null}</td>
              <td className="px-3 py-2.5 text-right">{canChange && <EditDate row={r} />}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One store: its latest capping, a way to set a new one from a date (administrators and managers), and the record of every change. */
export function StoreCappingPanel({ row, canChange, onClose }: { row: CapRow; canChange: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const today = istToday();
  const [text, setText] = useState("");
  const [date, setDate] = useState(today);
  const [confirming, setConfirming] = useState(false);
  const capping = text === "" ? null : Number(text);
  const cappingBad = capping !== null && (!Number.isInteger(capping) || capping < 1 || capping > MAX);
  const dateBad = !date || date > today || date < EARLIEST;
  const ready = capping !== null && !cappingBad && !dateBad;

  const save = useMutation({
    mutationFn: () => changeCapping(row.storeId, capping as number, date),
    onSuccess: (r) => {
      pushToast(`Capping for ${row.outletName} set to ${r.capping} from ${dateLabel(r.effectiveFrom)}${r.backdated ? " (backdated)" : ""}.`, "success");
      setText("");
      setConfirming(false);
      void qc.invalidateQueries({ queryKey: ["capping"] });
    },
    onError: () => setConfirming(false),            // the error toast is already shown by the API layer
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready || save.isPending) return;
    if (isBackdated(date, today)) setConfirming(true);
    else save.mutate();
  }

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-4 shadow-card" aria-label={`Capping for ${row.outletName}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-extrabold text-heading">{row.outletName}</h3>
          <p className="text-xs text-gray-500">{row.outletId}{row.city ? ` · ${row.city}` : ""}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close" className="rounded px-2 text-xl leading-none text-gray-400 hover:text-gray-700">×</button>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-brand-500/5 px-3 py-2 ring-1 ring-brand-500/20">
        {row.capping === null ? (
          <span className="text-sm text-gray-600">No capping is set for this store yet.</span>
        ) : (
          <span className="text-sm text-gray-700">Latest capping <b className="text-base tabular-nums text-heading">{row.capping}</b> a day{row.since ? <>, since <b>{dateLabel(row.since)}</b></> : null}</span>
        )}
      </div>

      {canChange ? (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            New capping (per day)
            <input className={field} inputMode="numeric" value={text} onChange={(e) => setText(e.target.value.replace(/[^\d]/g, ""))} placeholder="e.g. 11" aria-invalid={cappingBad} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Starts on
            <input className={field} type="date" value={date} min={EARLIEST} max={today} onChange={(e) => setDate(e.target.value)} aria-invalid={dateBad} />
          </label>
          <Button type="submit" disabled={!ready} isLoading={save.isPending}>Update capping</Button>
        </form>
      ) : (
        <p className="text-xs text-gray-500">Only an administrator or manager can change capping. You can read each store&rsquo;s history here.</p>
      )}
      {canChange && cappingBad && <p role="alert" className="-mt-2 text-sm text-status-danger">Enter a whole number from 1 to 1,000,000.</p>}
      {canChange && dateBad && <p role="alert" className="-mt-2 text-sm text-status-danger">Choose today or an earlier date.</p>}

      <div>
        <h4 className="mb-2 text-sm font-bold text-gray-900">History</h4>
        <History storeId={row.storeId} canChange={canChange} />
      </div>

      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Set the capping from a past date?"
        description="This is not today's date."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
            <Button onClick={() => save.mutate()} isLoading={save.isPending}>Yes, set it</Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          {row.outletName} will have a capping of <b>{capping}</b> a day from <b>{date ? dateLabel(date) : ""}</b>. A change cannot be removed afterwards, but you can move its start date.
        </p>
      </Modal>
    </section>
  );
}
