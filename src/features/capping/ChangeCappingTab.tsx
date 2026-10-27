import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { dateLabel, isBackdated, istToday } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import { usePermission } from "@/hooks/usePermission";
import { pushToast } from "@/lib/toast";
import { changeCapping, getCappingHistory, type CapRow } from "@/services/capping";

const MAX = 1_000_000;
const EARLIEST = "2024-01-01";

function History({ storeId }: { storeId: string }) {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["capping", "history", storeId],
    queryFn: () => getCappingHistory(storeId),
    staleTime: 15_000,
  });
  if (isLoading) return <Skeleton className="h-32" />;
  if (isError) return <ErrorState message={error instanceof Error ? error.message : "Couldn't load the history."} onRetry={() => refetch()} />;
  if (!data || data.rows.length === 0) {
    return <EmptyState title="No changes recorded yet" description="Once a capping is set for this store, each change appears here with the date it took effect." />;
  }
  const inForce = data.rows.find((r) => r.effectiveFrom <= data.today)?.id;     // rows are newest first
  return (
    <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
      <table className="w-full min-w-[520px] border-collapse text-sm">
        <thead>
          <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
            {["Capping", "Effective from", "Changed by", "Created at"].map((h) => <th key={h} className="border-b border-surface-border px-3 py-3 first:pl-4">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-border/60">
              <td className="px-3 py-3 pl-4 font-semibold tabular-nums">
                {r.capping} {r.id === inForce && <Badge tone="success">In force today</Badge>}
              </td>
              <td className="px-3 py-3 tabular-nums">{dateLabel(r.effectiveFrom)}</td>
              <td className="px-3 py-3 text-gray-700">{r.changedBy ?? "—"}{r.changedByCode ? <span className="text-xs text-gray-500"> ({r.changedByCode})</span> : null}</td>
              <td className="px-3 py-3 text-gray-600">{new Date(r.createdAt).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Change a store's capping from a date (administrators and managers), and read the store's history (everyone who can see capping). */
export function ChangeCappingTab({ rows }: { rows: CapRow[] }) {
  const canChange = usePermission("capping.change");
  const qc = useQueryClient();
  const today = istToday();
  const [storeId, setStoreId] = useState("");
  const [text, setText] = useState("");
  const [date, setDate] = useState(today);
  const [confirming, setConfirming] = useState(false);

  const options = useMemo(
    () => [...rows].sort((a, b) => a.outletName.localeCompare(b.outletName)).map((r) => ({ value: r.storeId, label: `${r.outletName} (${r.outletId})${r.city ? ` · ${r.city}` : ""}` })),
    [rows],
  );
  const store = rows.find((r) => r.storeId === storeId) ?? null;
  const capping = text === "" ? null : Number(text);
  const cappingBad = capping !== null && (!Number.isInteger(capping) || capping < 1 || capping > MAX);
  const dateBad = !date || date > today || date < EARLIEST;
  const ready = !!storeId && capping !== null && !cappingBad && !dateBad;

  const save = useMutation({
    mutationFn: () => changeCapping(storeId, capping as number, date),
    onSuccess: (r) => {
      pushToast(`Capping for ${store?.outletName ?? "the store"} set to ${r.capping} from ${dateLabel(r.effectiveFrom)}${r.backdated ? " (backdated)" : ""}.`, "success");
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
    <div className="flex flex-col gap-5">
      <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card">
        <h3 className="text-sm font-bold text-gray-900">Change capping</h3>
        <p className="mt-1 text-xs text-gray-500">
          The new capping applies from the effective date until the next change. Earlier days keep the value they had. {canChange ? "" : "Only an administrator or manager can change capping; you can read each store's history here."}
        </p>
        <form onSubmit={submit} className="mt-4 grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Store
            <Dropdown value={storeId} onValueChange={setStoreId} options={options} placeholder="Search for a store…" searchable aria-label="Store" />
          </label>
          {canChange && (
            <>
              <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
                New capping (per day)
                <input className={field} inputMode="numeric" value={text} onChange={(e) => setText(e.target.value.replace(/[^\d]/g, ""))} placeholder="e.g. 11" aria-invalid={cappingBad} />
              </label>
              <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
                Effective from
                <input className={field} type="date" value={date} min={EARLIEST} max={today} onChange={(e) => setDate(e.target.value)} aria-invalid={dateBad} />
              </label>
              <Button type="submit" disabled={!ready} isLoading={save.isPending}>Save capping</Button>
            </>
          )}
        </form>
        {canChange && cappingBad && <p role="alert" className="mt-2 text-sm text-status-danger">Enter a whole number from 1 to 1,000,000.</p>}
        {canChange && dateBad && <p role="alert" className="mt-2 text-sm text-status-danger">Choose today or an earlier date.</p>}
        {canChange && store && store.dailyCap !== null && <p className="mt-2 text-xs text-gray-500">Current capping for {store.outletName}: <b>{store.dailyCap}</b> a day.</p>}
      </section>

      <section className="flex flex-col gap-3" aria-label="Capping history">
        <h3 className="text-sm font-bold text-gray-900">{store ? `History · ${store.outletName}` : "History"}</h3>
        {storeId ? <History storeId={storeId} /> : <EmptyState title="Choose a store" description="Pick a store above to see when its capping changed and who changed it." />}
      </section>

      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Change the capping for a past date?"
        description="This is not today's date."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
            <Button onClick={() => save.mutate()} isLoading={save.isPending}>Yes, change it</Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          {store?.outletName} will show a capping of <b>{capping}</b> a day from <b>{date ? dateLabel(date) : ""}</b>. The capping sheet changes for every day since then, up to the next change already recorded.
          A change cannot be edited or removed afterwards.
        </p>
      </Modal>
    </div>
  );
}
