import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useEditEntry, useReviewEntry, useTimeline, type EntryRow, type TimelineEvent } from "@/features/entries/api";
import { EVENT_LABEL, FIELD_LABEL, FLAG_LABEL, fmtDay, fmtMoment, fmtValue, roleLabel } from "@/features/entries/format";

const TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  CREATED: "success", RESTORED: "success", BASELINE: "neutral", EDITED: "warning", CLEARED: "danger",
  REVIEWED: "info", FLAGGED: "danger", NEEDS_CORRECTION: "danger", STATUS_CHANGED: "neutral",
};

function Changes({ e }: { e: TimelineEvent }) {
  const fields = e.changed_fields ?? Object.keys(e.new ?? {});
  if (!fields.length) return null;
  return (
    <table className="mt-2 w-full max-w-md text-xs">
      <tbody>
        {fields.map((f) => (
          <tr key={f} className="border-t border-surface-border/60">
            <td className="py-1 pr-3 font-semibold text-gray-600">{FIELD_LABEL[f] ?? f}</td>
            {e.old ? (
              <>
                <td className="py-1 pr-2 text-gray-500 line-through">{fmtValue(e.old[f])}</td>
                <td className="py-1 font-bold text-gray-900">→ {fmtValue(e.new?.[f])}</td>
              </>
            ) : (
              <td className="py-1 font-bold text-gray-900" colSpan={2}>{fmtValue(e.new?.[f])}</td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EntrySummary({ entry }: { entry: EntryRow }) {
  const c = entry.creator;
  return (
    <div className="grid gap-x-6 gap-y-2 rounded-xl bg-surface-subtle p-4 text-sm sm:grid-cols-2">
      <p><span className="text-gray-500">Store</span><br /><b>{entry.store?.name}</b> <span className="text-xs text-gray-500">{entry.store?.outlet_id}{entry.store?.crm_code ? ` · ${entry.store.crm_code}` : ""}</span></p>
      <p><span className="text-gray-500">Day</span><br /><b>{fmtDay(entry.order_date)}</b></p>
      <p><span className="text-gray-500">Original creator</span><br />
        {c?.verified ? (
          <><b>{c.name}</b> <span className="text-xs text-gray-500">({c.code}) · {roleLabel(c.role)}</span></>
        ) : (
          <><Badge tone="warning">Creator not verified</Badge> <span className="text-xs text-gray-500">{c?.last_recorded_marker ? `last recorded marker: ${c.last_recorded_marker}` : "no marker on record"}</span></>
        )}
      </p>
      <p><span className="text-gray-500">Created on the server</span><br /><b>{fmtMoment(entry.created_at)}</b>
        {entry.client_submitted_at && <span className="block text-xs text-gray-500">phone clock said {fmtMoment(entry.client_submitted_at)} (diagnosis only)</span>}</p>
      <p><span className="text-gray-500">Current number</span><br /><b className="text-lg">{entry.employee_count}</b>{entry.cash_adjustment ? <span className="text-xs text-gray-500"> + {entry.cash_adjustment} cash adjustment</span> : null}</p>
      <p><span className="text-gray-500">Last change</span><br />
        {entry.last_modified ? <><b>{entry.last_modified.by_name ?? "unknown"}</b> <span className="text-xs text-gray-500">{roleLabel(entry.last_modified.role)} · {fmtMoment(entry.last_modified.at)}</span></> : <span className="text-gray-500">never changed (version {entry.version})</span>}</p>
      {entry.flags && entry.flags.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 sm:col-span-2">{entry.flags.map((f) => <Badge key={f} tone={f === "flagged" || f === "needs_correction" ? "danger" : "neutral"}>{FLAG_LABEL[f] ?? f}</Badge>)}</p>
      )}
    </div>
  );
}

/** One entry's complete history, oldest first, with the correction form (Team Lead / administrator) and the review marks (reviewer / administrator). */
export function EntryHistoryModal({ entryId, onClose, canEdit, canReview }: { entryId: string; onClose: () => void; canEdit: boolean; canReview: boolean }) {
  const { data, isLoading, isError, error, refetch } = useTimeline(entryId);
  const edit = useEditEntry();
  const review = useReviewEntry();
  const [editing, setEditing] = useState(false);
  const [count, setCount] = useState("");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [note, setNote] = useState<string | null>(null);

  const entry = data?.entry;
  const valid = /^\d{1,3}$/.test(count) && Number(count) <= 200 && reason.trim().length >= 5;

  function submitEdit() {
    if (!entry || !valid) return;
    setNote(null);
    edit.mutate(
      { entryId, bottleCount: Number(count), reason: reason.trim(), expectedVersion: entry.version },
      {
        onSuccess: () => { setEditing(false); setReason(""); },
        onError: (e) => setNote(e instanceof Error ? e.message : "Couldn't save the correction."),
      },
    );
  }

  function mark(action: "reviewed" | "flagged" | "needs_correction" | "clear") {
    setNote(null);
    review.mutate({ entryId, action, comment }, {
      onSuccess: () => setComment(""),
      onError: (e) => setNote(e instanceof Error ? e.message : "Couldn't save the review."),
    });
  }

  return (
    <Modal open onClose={onClose} size="lg" title="Entry history" description={data?.store ? `${data.store.name} · ${data.store.outlet_id}` : undefined}
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message={error instanceof Error ? error.message : "Couldn't load this entry."} onRetry={() => refetch()} />}
      {data && (
        <div className="flex flex-col gap-5">
          {entry ? <EntrySummary entry={entry} /> : <p className="rounded-xl bg-status-danger-soft p-3 text-sm text-status-danger">This entry was removed. Its history is kept below.</p>}
          {!data.chain_ok && <p className="rounded-xl bg-status-danger-soft p-3 text-sm font-semibold text-status-danger">The integrity check of this history FAILED. Treat it as tampered with and tell the developer.</p>}

          <ol className="flex flex-col gap-4 border-l-2 border-surface-border pl-4">
            {data.events.map((e) => (
              <li key={e.id} className="relative">
                <span className="absolute -left-[1.45rem] top-1 h-3 w-3 rounded-full border-2 border-surface bg-brand-500" aria-hidden="true" />
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={TONE[e.type] ?? "neutral"}>{EVENT_LABEL[e.type] ?? e.type}</Badge>
                  <span className="text-sm font-semibold text-gray-900">{e.actor.known ? e.actor.name : "Unknown (direct database change)"}</span>
                  {e.actor.known && <span className="text-xs text-gray-500">{e.actor.code} · {roleLabel(e.actor.role)} at that time</span>}
                </div>
                <p className="text-xs text-gray-500">{fmtMoment(e.at)}{e.version ? ` · version ${e.version}` : ""}{e.source ? ` · ${e.source}` : ""}</p>
                <Changes e={e} />
                {e.reason && <p className="mt-1 text-sm text-gray-700"><span className="font-semibold">Reason:</span> {e.reason}</p>}
                {e.comment && e.comment !== e.reason && <p className="mt-1 text-sm text-gray-700"><span className="font-semibold">Comment:</span> {e.comment}</p>}
              </li>
            ))}
          </ol>

          {data.attempts.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-bold text-heading">Attempts to mark this store and day</h3>
              <ul className="flex flex-col gap-1.5 text-sm">
                {data.attempts.map((a, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-subtle px-3 py-2">
                    <Badge tone={a.outcome === "saved" ? "success" : a.outcome === "duplicate" ? "info" : "danger"}>{a.outcome === "duplicate" ? "same number sent again" : a.outcome}</Badge>
                    <span className="font-semibold">{a.user_name ?? "unknown"}</span>
                    <span className="text-xs text-gray-500">{a.user_code} · tried {a.bottle_count ?? "—"} · {fmtMoment(a.created_at)}{a.client ? ` · ${a.client}` : ""}</span>
                    {a.reason && <span className="basis-full text-xs text-gray-600">{a.reason}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {note && <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">{note}</p>}

          {entry && canEdit && entry.can_edit && (
            editing ? (
              <div className="flex flex-col gap-3 rounded-xl border border-surface-border p-4">
                <h3 className="text-sm font-bold text-heading">Correct this entry</h3>
                <p className="text-xs text-gray-500">The original number, your name, the time and your reason stay in the history. The creator does not change.</p>
                <Input label="Correct number of bottles" type="number" min={0} max={200} value={count} onChange={(e) => setCount(e.target.value)} />
                <Input label="Why is it being corrected? (required)" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. delivery note shows 14, entered 11" />
                <div className="flex gap-2">
                  <Button onClick={submitEdit} disabled={!valid} isLoading={edit.isPending}>Save correction</Button>
                  <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                </div>
              </div>
            ) : (
              <Button variant="secondary" onClick={() => { setCount(String(entry.employee_count ?? "")); setEditing(true); }}>Correct this entry</Button>
            )
          )}

          {entry && canReview && (
            <div className="flex flex-col gap-3 rounded-xl border border-surface-border p-4">
              <h3 className="text-sm font-bold text-heading">Review</h3>
              <p className="text-xs text-gray-500">Reviewing never changes the number or the creator. To change the number, flag it for the Team Lead or an administrator.</p>
              <Input label="Comment (needed to flag)" value={comment} onChange={(e) => setComment(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" isLoading={review.isPending} onClick={() => mark("reviewed")}>Mark reviewed</Button>
                <Button variant="danger" isLoading={review.isPending} onClick={() => mark("flagged")}>Flag</Button>
                <Button variant="secondary" isLoading={review.isPending} onClick={() => mark("needs_correction")}>Needs correction</Button>
                {entry.review && entry.review.status !== "none" && <Button variant="ghost" onClick={() => mark("clear")}>Clear mark</Button>}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
