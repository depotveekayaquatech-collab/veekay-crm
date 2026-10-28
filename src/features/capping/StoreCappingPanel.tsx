import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { dateLabel } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import { pushToast } from "@/lib/toast";
import { changeCapping, getCappingHistory, removeCapping, type CapRow } from "@/services/capping";

const MAX = 1_000_000;

/** The store's record: every capping it has had (and any removal), with the day it changed and who did it, newest first. */
function History({ storeId }: { storeId: string }) {
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ["capping", "history", storeId], queryFn: () => getCappingHistory(storeId), staleTime: 15_000 });
  if (isLoading) return <Skeleton className="h-32" />;
  if (isError) return <ErrorState message={error instanceof Error ? error.message : "Couldn't load the history."} onRetry={() => refetch()} />;
  if (!data) return null;
  if (data.rows.length === 0) return <EmptyState title="No changes recorded yet" description="Once a capping is set for this store, each change appears here." />;
  const inForce = data.rows.find((r) => r.effectiveFrom <= data.today)?.id;     // rows are newest first
  return (
    <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface">
      <table className="w-full min-w-[420px] border-collapse text-sm">
        <thead>
          <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
            {["Capping", "From", "Set by"].map((h) => <th key={h} className="border-b border-surface-border px-3 py-2.5 first:pl-4">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-border/60">
              <td className="px-3 py-2.5 pl-4 font-semibold tabular-nums">
                {r.capping === null ? <span className="text-gray-500">Removed</span> : r.capping} {r.id === inForce && <Badge tone="success">Now</Badge>}
              </td>
              <td className="px-3 py-2.5 tabular-nums">{dateLabel(r.effectiveFrom)}</td>
              <td className="px-3 py-2.5 text-gray-700">{r.changedBy ?? "—"}{r.changedByCode ? <span className="text-xs text-gray-500"> ({r.changedByCode})</span> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One store: its latest capping, a way to set a new one or remove it (administrators and managers), and the record of every change. No dates to choose. */
export function StoreCappingPanel({ row, canChange, onClose }: { row: CapRow; canChange: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [removing, setRemoving] = useState(false);
  const capping = text === "" ? null : Number(text);
  const cappingBad = capping !== null && (!Number.isInteger(capping) || capping < 1 || capping > MAX);
  const ready = capping !== null && !cappingBad;
  const done = () => void qc.invalidateQueries({ queryKey: ["capping"] });

  const save = useMutation({
    mutationFn: () => changeCapping(row.storeId, capping as number),
    onSuccess: (r) => {
      pushToast(`Capping for ${row.outletName} set to ${r.capping}.`, "success");
      setText("");
      done();
    },
  });
  const remove = useMutation({
    mutationFn: () => removeCapping(row.storeId),
    onSuccess: () => {
      pushToast(`Capping removed for ${row.outletName}.`, "success");
      setRemoving(false);
      done();
    },
    onError: () => setRemoving(false),            // the error toast is already shown by the API layer
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (ready && !save.isPending) save.mutate();
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

      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-lg bg-brand-500/5 px-3 py-2 ring-1 ring-brand-500/20">
        {row.capping === null ? (
          <span className="text-sm text-gray-600">No capping is set for this store.</span>
        ) : (
          <span className="text-sm text-gray-700">Latest capping <b className="text-base tabular-nums text-heading">{row.capping}</b> a day</span>
        )}
        {canChange && row.capping !== null && (
          <button type="button" onClick={() => setRemoving(true)} className="text-xs font-semibold text-status-danger hover:underline">Remove capping</button>
        )}
      </div>

      {canChange ? (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            {row.capping === null ? "Capping (per day)" : "New capping (per day)"}
            <input className={field} inputMode="numeric" value={text} onChange={(e) => setText(e.target.value.replace(/[^\d]/g, ""))} placeholder="e.g. 11" aria-invalid={cappingBad} />
          </label>
          <Button type="submit" disabled={!ready} isLoading={save.isPending}>Update capping</Button>
        </form>
      ) : (
        <p className="text-xs text-gray-500">Only an administrator or manager can change capping. You can read each store&rsquo;s history here.</p>
      )}
      {canChange && cappingBad && <p role="alert" className="-mt-2 text-sm text-status-danger">Enter a whole number from 1 to 1,000,000.</p>}

      <div>
        <h4 className="mb-2 text-sm font-bold text-gray-900">History</h4>
        <History storeId={row.storeId} />
      </div>

      <Modal
        open={removing}
        onClose={() => setRemoving(false)}
        title="Remove this store's capping?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRemoving(false)}>Cancel</Button>
            <Button variant="danger" onClick={() => remove.mutate()} isLoading={remove.isPending}>Yes, remove it</Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          {row.outletName} will have no capping from today. The days before keep the capping they had, and the history shows the removal. You can set a capping again at any time.
        </p>
      </Modal>
    </section>
  );
}
