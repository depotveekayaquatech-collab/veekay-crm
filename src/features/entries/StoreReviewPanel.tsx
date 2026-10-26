import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { StoreSummary } from "@/features/orders/StoreSummary";
import { useStoreReview, useVerifyStore, type StoreReviewDay, type StoreReviewScope } from "@/features/entries/api";
import { VERIFICATION_SHORT, type Verification } from "@/features/entries/format";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// A day's colour is where its entry stands: waiting for the Team Lead, verified by them, or reviewed. A flagged day carries a dot.
const TONE: Record<Verification, string> = {
  submitted: "border-status-warning/30 bg-status-warning-soft text-status-warning",
  verified_l2: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  reviewed_l3: "border-status-success/25 bg-status-success/15 text-status-success",
};

function Chevron({ dir }: { dir: "left" | "right" }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={dir === "left" ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6"} />
    </svg>
  );
}

function Day({ d, onOpen }: { d: StoreReviewDay; onOpen: (entryId: string) => void }) {
  const e = d.entry;
  const base = "relative flex h-14 flex-col items-center justify-center rounded-lg border text-sm transition-[transform,box-shadow] sm:h-[4.25rem]";
  const today = d.is_today ? "ring-2 ring-brand-400 ring-offset-1" : "";
  if (!e) {
    return (
      <div className={`${base} ${d.is_future ? "border-transparent bg-surface-subtle text-gray-300" : "border-dashed border-gray-300 text-gray-400"} ${today}`}>
        <span className="absolute left-1.5 top-1 text-[10px] font-semibold opacity-70">{d.day}</span>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onOpen(e.entry_id)}
      title={`${e.count} bottles · ${VERIFICATION_SHORT[e.status]}${e.created_by ? ` · entered by ${e.created_by}` : ""}${e.requested ? " · verification requested" : ""}${e.flagged ? " · flagged" : ""}${e.edited ? " · edited" : ""}`}
      className={`${base} ${TONE[e.status]} ${today} hover:scale-[1.04] hover:shadow-md`}
    >
      <span className="absolute left-1.5 top-1 text-[10px] font-semibold opacity-70">{d.day}</span>
      <span className="text-base font-bold tabular-nums">{e.count}</span>
      {e.flagged && <span className="absolute bottom-1 right-1.5 h-2 w-2 rounded-full bg-status-danger" aria-label="Flagged" />}
      {e.requested && !e.flagged && <span className="absolute bottom-1 right-1.5 h-2 w-2 rounded-full bg-brand-500" aria-label="Verification requested" />}
    </button>
  );
}

/**
 * The store a Team Lead or Reviewer opened to check: the same store card and month calendar the employee works in, coloured by where each entry stands, and
 * ONE button that verifies the whole store, so nobody has to mark every entry one by one. "Verify store" means "I checked every entry in view": it covers the
 * chosen employee's entries (when one is chosen) and the chosen days, and leaves entries somebody flagged for a separate look.
 */
export function StoreReviewPanel({ scope, onOpenEntry }: { scope: StoreReviewScope; onOpenEntry: (entryId: string) => void }) {
  const [period, setPeriod] = useState<{ year?: number; month?: number }>({});
  const [confirm, setConfirm] = useState(false);
  const [comment, setComment] = useState("");
  const q = useStoreReview(scope, period);
  const verify = useVerifyStore();

  if (q.isLoading) return <Skeleton className="h-96" />;
  if (q.isError || !q.data) return <ErrorState message={q.error instanceof Error ? q.error.message : "Couldn't open this store."} onRetry={() => q.refetch()} />;
  const r = q.data;
  const s = r.store;
  const shown = r.days.filter((d) => d.entry);
  const bottles = shown.reduce((n, d) => n + (d.entry?.count ?? 0), 0);
  const now = new Date();
  const atCurrent = r.year === now.getFullYear() && r.month === now.getMonth() + 1;
  const step = (by: number) => {
    const d = new Date(r.year, r.month - 1 + by, 1);
    setPeriod({ year: d.getFullYear(), month: d.getMonth() + 1 });
  };
  const reviewing = r.verify.to === "reviewed_l3";
  const verb = reviewing ? "Mark store reviewed" : "Verify store";
  const todo = r.verify.will_change;

  async function submit() {
    await verify.mutateAsync({ ...scope, comment });
    setConfirm(false);
    setComment("");
  }

  return (
    <div className="flex flex-col gap-4">
      <StoreSummary
        store={{ name: s.name, externalCode: s.outlet_id, crmCode: s.crm_code, city: s.city, state: s.state, partnerName: s.platform, regionName: s.region_name,
          pocName: s.poc_name, pocNumber: s.poc_number, vendorName: s.vendor_name, vendorNumber: s.vendor_number }}
      />

      {r.verify.allowed && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-brand-200 bg-brand-50/60 px-4 py-3.5 sm:px-5">
          <div className="min-w-0 text-sm">
            <p className="font-bold text-heading">
              {todo > 0 ? `${todo} entr${todo === 1 ? "y" : "ies"} of this store ${reviewing ? "are not reviewed yet" : "are waiting for your check"}` : "Every entry of this store in view is already checked"}
            </p>
            <p className="text-xs text-gray-600">
              One click {reviewing ? "marks them all reviewed" : "verifies them all"}: you do not need to open each entry.
              {r.verify.skipped_flagged > 0 && ` ${r.verify.skipped_flagged} flagged entr${r.verify.skipped_flagged === 1 ? "y is" : "ies are"} left out so you can look at ${r.verify.skipped_flagged === 1 ? "it" : "them"} yourself.`}
              {scope.creatorId ? " Only this employee's entries." : ""}
            </p>
          </div>
          <Button onClick={() => setConfirm(true)} disabled={todo === 0}>{verb}</Button>
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border px-4 py-3.5 sm:px-5">
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => step(-1)} aria-label="Previous month" className="rounded-md p-1.5 text-gray-500 hover:bg-surface-muted hover:text-gray-900"><Chevron dir="left" /></button>
            <h3 className="min-w-[9rem] text-center text-base font-extrabold text-heading">{MONTHS[r.month - 1]} {r.year}</h3>
            <button type="button" onClick={() => step(1)} disabled={atCurrent} aria-label="Next month"
              className="rounded-md p-1.5 text-gray-500 hover:bg-surface-muted hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"><Chevron dir="right" /></button>
            {!atCurrent && <button type="button" onClick={() => setPeriod({})} className="ml-1 rounded-md px-2 py-1 text-xs font-semibold text-brand-600 hover:bg-brand-50">Today</button>}
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-status-warning" /> Waiting for Team Lead</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-sky-500" /> Verified</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-status-success" /> Reviewed</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm border border-dashed border-gray-400" /> No entry</span>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-y divide-surface-border border-b border-surface-border sm:grid-cols-4 sm:divide-y-0">
          {[
            { label: "Bottles", value: bottles.toLocaleString(), tone: "text-heading" },
            { label: "Days with an entry", value: `${shown.length}/${r.days.filter((d) => !d.is_future).length}`, tone: "text-heading" },
            { label: "Waiting for Team Lead", value: r.counts.pending_l2, tone: r.counts.pending_l2 > 0 ? "text-status-warning" : "text-status-success" },
            { label: "Reviewed", value: `${r.counts.reviewed_l3}/${r.counts.entries}`, tone: "text-heading" },
          ].map((c) => (
            <div key={c.label} className="px-4 py-3 sm:px-5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{c.label}</p>
              <p className={`mt-0.5 text-lg font-bold tabular-nums ${c.tone}`}>{c.value}</p>
            </div>
          ))}
        </div>

        <div className="p-3 sm:p-5">
          <div className="grid grid-cols-7 gap-1.5 text-center text-[11px] font-semibold uppercase tracking-wide text-gray-400 sm:gap-2">
            {WEEKDAYS.map((w) => <div key={w} className="pb-1">{w}</div>)}
          </div>
          <div className="mt-1 grid grid-cols-7 gap-1.5 sm:gap-2">
            {Array.from({ length: new Date(r.year, r.month - 1, 1).getDay() }).map((_, i) => <div key={`b${i}`} />)}
            {r.days.map((d) => <Day key={d.date} d={d} onOpen={onOpenEntry} />)}
          </div>
          <p className="mt-3 text-xs text-gray-500">Tap a day to open that entry: see who entered it, correct it, or read its history.</p>
        </div>
      </div>

      <Modal
        open={confirm}
        onClose={() => !verify.isPending && setConfirm(false)}
        size="sm"
        title={`${verb}?`}
        description={`${s.name}${scope.creatorId ? " · this employee's entries" : ""}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(false)} disabled={verify.isPending}>Cancel</Button>
            <Button onClick={() => void submit().catch(() => undefined)} isLoading={verify.isPending}>{reviewing ? `Review ${todo}` : `Verify ${todo}`}</Button>
          </>
        }
      >
        <div className="flex flex-col gap-3 text-sm text-gray-700">
          <p>
            This {reviewing ? "marks" : "verifies"} <b>{todo}</b> entr{todo === 1 ? "y" : "ies"} as checked by you, and it is kept in each entry's history. No number changes.
          </p>
          <Input label="Note (optional)" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="e.g. matched with the vendor sheet" maxLength={1000} />
          {verify.isError && <p className="text-sm text-status-danger">{verify.error instanceof Error ? verify.error.message : "Couldn't verify the store."}</p>}
        </div>
      </Modal>
    </div>
  );
}
