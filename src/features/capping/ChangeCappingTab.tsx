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
import { changeCapping, getCappingHistory, markZeroDays, unmarkZeroDay, type CapRow } from "@/services/capping";

const MAX = 1_000_000;
const EARLIEST = "2024-01-01";

function ZeroDays({ storeId, canChange, days }: { storeId: string; canChange: boolean; days: { id: string; day: string; changedBy: string | null }[] }) {
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (day: string) => unmarkZeroDay(storeId, day),
    onSuccess: () => {
      pushToast("Day taken back to its normal capping.", "success");
      void qc.invalidateQueries({ queryKey: ["capping"] });
    },
  });
  if (days.length === 0) return null;
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-4 shadow-card">
      <h4 className="text-sm font-bold text-gray-900">Days with 0 capping</h4>
      <ul className="mt-2 flex flex-wrap gap-2">
        {days.map((z) => (
          <li key={z.id} className="flex items-center gap-1.5 rounded-full bg-surface-subtle px-3 py-1 text-sm ring-1 ring-surface-border" title={z.changedBy ? `Marked by ${z.changedBy}` : undefined}>
            <span className="font-semibold tabular-nums">{dateLabel(z.day)}</span>
            {canChange && (
              <button onClick={() => remove.mutate(z.day)} disabled={remove.isPending} aria-label={`Take ${dateLabel(z.day)} back to its normal capping`} className="rounded px-1 text-gray-400 hover:text-status-danger">×</button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function History({ storeId, canChange }: { storeId: string; canChange: boolean }) {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["capping", "history", storeId],
    queryFn: () => getCappingHistory(storeId),
    staleTime: 15_000,
  });
  if (isLoading) return <Skeleton className="h-32" />;
  if (isError) return <ErrorState message={error instanceof Error ? error.message : "Couldn't load the history."} onRetry={() => refetch()} />;
  if (!data) return null;
  const zero = <ZeroDays storeId={storeId} canChange={canChange} days={data.zeroDays ?? []} />;
  if (data.rows.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <EmptyState title="No changes recorded yet" description="Once a capping is set for this store, each change appears here with the date it took effect." />
        {zero}
      </div>
    );
  }
  const inForce = data.rows.find((r) => r.effectiveFrom <= data.today)?.id;     // rows are newest first
  return (
    <div className="flex flex-col gap-3">
    {zero}
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
    </div>
  );
}

/** Mark a store's capping as 0 on chosen days: pick days one by one, then save. The days either side keep their capping. */
function ZeroDaysForm({ storeId, storeName }: { storeId: string; storeName: string }) {
  const qc = useQueryClient();
  const today = istToday();
  const [pick, setPick] = useState(today);
  const [days, setDays] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);

  const save = useMutation({
    mutationFn: () => markZeroDays(storeId, days),
    onSuccess: (r) => {
      pushToast(`${r.marked.length} day${r.marked.length === 1 ? "" : "s"} marked as 0 capping for ${storeName}${r.already.length ? ` (${r.already.length} already marked)` : ""}.`, "success");
      setDays([]);
      setConfirming(false);
      void qc.invalidateQueries({ queryKey: ["capping"] });
    },
    onError: () => setConfirming(false),
  });
  const add = () => {
    if (pick && !days.includes(pick)) setDays([...days, pick].sort());
  };

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card" aria-label="Mark 0 capping for specific days">
      <h3 className="text-sm font-bold text-gray-900">Mark 0 capping for specific days</h3>
      <p className="mt-1 text-xs text-gray-500">The capping is 0 on the days you add, and counts as 0 in the average. The days before and after keep their normal capping.</p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Day
          <input className={`${field} w-48`} type="date" value={pick} min="2024-01-01" onChange={(e) => setPick(e.target.value)} />
        </label>
        <Button variant="secondary" onClick={add} disabled={!pick || days.includes(pick)}>Add day</Button>
      </div>
      {days.length > 0 && (
        <>
          <ul className="mt-3 flex flex-wrap gap-2">
            {days.map((d) => (
              <li key={d} className="flex items-center gap-1.5 rounded-full bg-brand-500/10 px-3 py-1 text-sm ring-1 ring-brand-500/25">
                <span className="font-semibold tabular-nums">{dateLabel(d)}</span>
                <button onClick={() => setDays(days.filter((x) => x !== d))} aria-label={`Remove ${dateLabel(d)}`} className="rounded px-1 text-gray-500 hover:text-status-danger">×</button>
              </li>
            ))}
          </ul>
          <div className="mt-3">
            <Button onClick={() => setConfirming(true)} isLoading={save.isPending}>Mark 0 capping for {days.length} day{days.length === 1 ? "" : "s"}</Button>
          </div>
        </>
      )}
      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Mark these days as 0 capping?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
            <Button onClick={() => save.mutate()} isLoading={save.isPending}>Yes, mark them</Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          {storeName} will have a capping of <b>0</b> on {days.map(dateLabel).join(", ")}. The capping sheet and the average capping change for those days. You can take a day back afterwards.
        </p>
      </Modal>
    </section>
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

      {canChange && storeId && <ZeroDaysForm key={storeId} storeId={storeId} storeName={store?.outletName ?? "The store"} />}

      <section className="flex flex-col gap-3" aria-label="Capping history">
        <h3 className="text-sm font-bold text-gray-900">{store ? `History · ${store.outletName}` : "History"}</h3>
        {storeId ? <History storeId={storeId} canChange={canChange} /> : <EmptyState title="Choose a store" description="Pick a store above to see when its capping changed and who changed it." />}
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
