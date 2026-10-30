import { useEffect, useRef, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { IconClose } from "@/components/ui/icons";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import {
  useAddComment, useEditEntry, useRequestCheck, useReviewEntry, useTimeline, useVerifyEntry, type EntryRow,
} from "@/features/entries/api";
import { FLAG_LABEL, VERIFICATION_LABEL, VERIFICATION_TONE, fmtDay, fmtMoment, roleLabel, type Verification } from "@/features/entries/format";
import { buildComments, buildTimeline, type TimelineItem } from "@/features/entries/timeline";

const DOT: Record<Verification, string> = { submitted: "bg-amber-500", verified_l2: "bg-sky-500", reviewed_l3: "bg-emerald-500" };
const RING: Record<Verification, string> = { submitted: "ring-amber-500/30", verified_l2: "ring-sky-500/30", reviewed_l3: "ring-emerald-500/30" };

function Card({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-surface-border bg-surface shadow-xs">
      <header className="flex items-center justify-between gap-2 border-b border-surface-border px-4 py-3">
        <h3 className="text-sm font-bold text-heading">{title}</h3>
        {aside}
      </header>
      <div className="px-4 py-3.5">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold text-gray-500">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-gray-900">{children}</dd>
    </div>
  );
}

function Details({ entry }: { entry: EntryRow }) {
  const c = entry.creator;
  const v = entry.verification;
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      <Field label="Date"><b>{fmtDay(entry.order_date)}</b></Field>
      <Field label="Store">
        <b>{entry.store?.name}</b>
        <span className="block text-xs text-gray-500">{entry.store?.outlet_id}{entry.store?.crm_code ? ` · ${entry.store.crm_code}` : ""}{entry.store?.platform ? ` · ${entry.store.platform}` : ""}</span>
      </Field>
      <Field label="Employee">
        {c?.verified ? (
          <><b>{c.name}</b><span className="block text-xs text-gray-500">{c.code} · {roleLabel(c.role)}</span></>
        ) : (
          <><Badge tone="warning">Creator not verified</Badge><span className="block text-xs text-gray-500">{c?.last_recorded_marker ? `last recorded marker: ${c.last_recorded_marker}` : "no creator on record"}</span></>
        )}
      </Field>
      <Field label="Quantity (bottles)">
        <b className="text-lg tabular-nums">{entry.employee_count}</b>
        {entry.cash_adjustment ? <span className="text-xs text-gray-500"> + {entry.cash_adjustment} cash adjustment = {entry.bottle_count} final</span> : null}
      </Field>
      <Field label="Created">
        {fmtMoment(entry.created_at)}
        {entry.client_submitted_at && <span className="block text-xs text-gray-500">phone clock said {fmtMoment(entry.client_submitted_at)} (diagnosis only)</span>}
      </Field>
      <Field label="Remarks">
        {entry.last_modified ? <>Last changed by <b>{entry.last_modified.by_name ?? "unknown"}</b> ({roleLabel(entry.last_modified.role)}), {fmtMoment(entry.last_modified.at)}</> : <span className="text-gray-500">Never changed (version {entry.version})</span>}
        {v?.check_requested && (
          <span className="mt-1 block rounded-md bg-amber-500/10 px-2 py-1 text-xs text-amber-800 dark:text-amber-300">
            <b>{v.check_requested.by_name ?? "A Reviewer"}</b> asked the Team Lead to check this{v.check_requested.note ? `: "${v.check_requested.note}"` : "."}
          </span>
        )}
      </Field>
      {entry.flags && entry.flags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 sm:col-span-2">
          {entry.flags.map((f) => <Badge key={f} tone={f === "flagged" || f === "needs_correction" ? "danger" : "neutral"}>{FLAG_LABEL[f] ?? f}</Badge>)}
        </div>
      )}
    </dl>
  );
}

function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <ol className="flex flex-col">
      {items.map((it, i) => (
        <li key={it.key} className="relative flex gap-3 pb-4 last:pb-0">
          {i < items.length - 1 && <span className="absolute left-[7px] top-4 h-[calc(100%-0.25rem)] w-0.5 bg-surface-border" aria-hidden="true" />}
          <span
            className={`relative mt-1 h-4 w-4 shrink-0 rounded-full border-2 border-surface ${it.state ? DOT[it.state] : "bg-gray-400"} ${it.current ? `ring-4 ${it.state ? RING[it.state] : "ring-gray-400/30"}` : ""}`}
            aria-label={it.current ? "Current state" : undefined}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-sm font-semibold text-gray-900">Status {it.n}:</span>
              <Badge tone={it.tone}>{it.label}</Badge>
              {it.current && <span className="text-[11px] font-bold text-brand-600">current</span>}
            </div>
            <p className="mt-0.5 text-xs text-gray-500">
              {fmtMoment(it.at)} · by <span className="font-medium text-gray-700">{it.actor.known ? it.actor.name : "unknown (direct database change)"}</span>
              {it.actor.known && ` (${roleLabel(it.actor.role)})`}
            </p>
            {it.changes.length > 0 && (
              <div className="mt-1.5 flex flex-col gap-1">
                {it.changes.map((c) => (
                  <p key={c.field} className="text-xs text-gray-600">
                    <span className="font-semibold">{c.label}:</span>{" "}
                    {c.old !== null && <><span className="rounded bg-status-danger-soft px-1.5 py-0.5 text-status-danger line-through">{c.old}</span> → </>}
                    <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-bold text-emerald-800 dark:text-emerald-300">{c.neu}</span>
                  </p>
                ))}
              </div>
            )}
            {it.reason && it.label !== "Submitted" && <p className="mt-1 text-xs text-gray-600"><span className="font-semibold">Reason:</span> {it.reason}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

/**
 * The right-hand verification panel for one entry (store + date): Details, Status timeline and Comments, with the actions the signed-in person's level allows.
 * Every action answers with the entry's new state, so the panel and the table behind it update without a page reload.
 */
export function EntryDrawer({ entryId, onClose }: { entryId: string; onClose: () => void }) {
  const { data, isLoading, isError, error, refetch } = useTimeline(entryId);
  const edit = useEditEntry();
  const verify = useVerifyEntry();
  const review = useReviewEntry();
  const request = useRequestCheck();
  const addComment = useAddComment();
  const panel = useRef<HTMLDivElement>(null);

  const [mode, setMode] = useState<"none" | "edit" | "request" | "flag">("none");
  const [count, setCount] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [comment, setComment] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; previous?.focus?.(); };
  }, [onClose]);

  const entry = data?.entry;
  const act = entry?.actions;
  const status = entry?.verification?.status ?? "submitted";
  const pending = edit.isPending || verify.isPending || review.isPending || request.isPending;
  const fail = (e: unknown, fallback: string) => setProblem(e instanceof Error ? e.message : fallback);
  const done = () => { setMode("none"); setProblem(null); setReason(""); setNote(""); };
  const items = data ? buildTimeline(data.events) : [];
  const comments = data ? buildComments(data.events) : [];
  const valid = /^\d{1,3}$/.test(count) && Number(count) <= 200 && reason.trim().length >= 5;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 animate-fade-in bg-ink-950/45 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div
        ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Entry verification"
        className="relative flex h-full w-full max-w-[600px] animate-slide-in-right flex-col bg-surface-subtle shadow-lg outline-none"
      >
        <header className="border-b border-surface-border bg-surface px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-gray-500">Entry verification</p>
              <h2 className="truncate text-lg font-extrabold text-heading">{data?.store?.name ?? (isLoading ? "Loading…" : "Entry")}</h2>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {data?.store?.entity && <Badge tone="neutral">{data.store.entity}</Badge>}
                {entry?.store?.platform && <Badge tone="info">{entry.store.platform}</Badge>}
                {entry && <Badge tone={VERIFICATION_TONE[status]} dot>{VERIFICATION_LABEL[status]}</Badge>}
                {entry?.verification?.check_requested && <Badge tone="warning">Verification requested</Badge>}
                {entry && <span className="text-xs text-gray-500">{fmtDay(entry.order_date)}</span>}
              </div>
            </div>
            <button onClick={onClose} aria-label="Close" className="-mr-1.5 -mt-1 rounded-md p-1.5 text-gray-400 hover:bg-surface-subtle hover:text-gray-700">
              <IconClose className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          {entry && act && (
            <div className="mt-3.5 flex flex-wrap gap-2">
              {act.edit && <Button size="sm" variant="secondary" disabled={pending} onClick={() => { setCount(String(entry.employee_count ?? "")); setMode(mode === "edit" ? "none" : "edit"); setProblem(null); }}>Edit</Button>}
              {act.verify && <Button size="sm" isLoading={verify.isPending} disabled={pending} onClick={() => verify.mutate({ entryId }, { onSuccess: done, onError: (e) => fail(e, "Couldn't verify.") })}>Verify</Button>}
              {act.review && (
                <Button size="sm" isLoading={review.isPending} disabled={pending} onClick={() => review.mutate({ entryId, action: "reviewed" }, { onSuccess: done, onError: (e) => fail(e, "Couldn't save the review.") })}>
                  {status === "submitted" ? "Review Myself" : "Mark Reviewed"}
                </Button>
              )}
              {act.request_check && <Button size="sm" variant="secondary" disabled={pending} onClick={() => { setMode(mode === "request" ? "none" : "request"); setProblem(null); }}>Request Team Lead to Check</Button>}
              {act.flag && <Button size="sm" variant="ghost" disabled={pending} onClick={() => { setMode(mode === "flag" ? "none" : "flag"); setProblem(null); }}>Flag…</Button>}
            </div>
          )}
        </header>

        <div className="flex-1 overflow-y-auto overscroll-contain p-4">
          {isLoading && <div className="flex flex-col gap-3"><Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-32" /></div>}
          {isError && <ErrorState message={error instanceof Error ? error.message : "Couldn't load this entry."} onRetry={() => refetch()} />}
          {data && (
            <div className="flex flex-col gap-4">
              {!data.chain_ok && <p className="rounded-xl bg-status-danger-soft p-3 text-sm font-semibold text-status-danger">The integrity check of this history FAILED. Treat it as tampered with and tell the developer.</p>}
              {!entry && <p className="rounded-xl bg-status-danger-soft p-3 text-sm text-status-danger">This entry was removed. Its history is kept below.</p>}
              {problem && <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">{problem}</p>}

              {entry && mode === "edit" && (
                <div className="flex flex-col gap-3 rounded-2xl border border-brand-500/30 bg-surface p-4">
                  <h3 className="text-sm font-bold text-heading">Edit this entry</h3>
                  <p className="text-xs text-gray-500">
                    {status === "submitted" && act?.verify ? "Saving a correction also verifies it. " : act?.review ? "A Reviewer's number is final. " : ""}
                    The old number, your name, the time and your reason stay in the history; the creator does not change.
                  </p>
                  <Input label="Correct number of bottles" type="number" min={0} max={200} value={count} onChange={(e) => setCount(e.target.value)} />
                  <Input label="Why is it being corrected? (required)" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. delivery note shows 14, entered 11" />
                  <div className="flex gap-2">
                    <Button size="sm" disabled={!valid} isLoading={edit.isPending}
                      onClick={() => edit.mutate({ entryId, bottleCount: Number(count), reason: reason.trim(), expectedVersion: entry.version }, { onSuccess: done, onError: (e) => fail(e, "Couldn't save the correction.") })}>
                      Save correction
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setMode("none")}>Cancel</Button>
                  </div>
                </div>
              )}

              {entry && mode === "request" && (
                <div className="flex flex-col gap-3 rounded-2xl border border-brand-500/30 bg-surface p-4">
                  <h3 className="text-sm font-bold text-heading">Ask the Team Lead to check this entry</h3>
                  <p className="text-xs text-gray-500">It appears in their pending list as "Verification requested", and they get a notification. You can still review it yourself.</p>
                  <Input label="What should they look at? (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                  <div className="flex gap-2">
                    <Button size="sm" isLoading={request.isPending} onClick={() => request.mutate({ entryId, note: note.trim() }, { onSuccess: done, onError: (e) => fail(e, "Couldn't send the request.") })}>Send request</Button>
                    <Button size="sm" variant="ghost" onClick={() => setMode("none")}>Cancel</Button>
                  </div>
                </div>
              )}

              {entry && mode === "flag" && (
                <div className="flex flex-col gap-3 rounded-2xl border border-surface-border bg-surface p-4">
                  <h3 className="text-sm font-bold text-heading">Flag this entry</h3>
                  <p className="text-xs text-gray-500">A flag never changes the number or the creator. Say what looks wrong.</p>
                  <Input label="What is wrong? (required)" value={note} onChange={(e) => setNote(e.target.value)} />
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="danger" disabled={note.trim().length < 5} isLoading={review.isPending}
                      onClick={() => review.mutate({ entryId, action: "flagged", comment: note.trim() }, { onSuccess: done, onError: (e) => fail(e, "Couldn't flag it.") })}>Flag</Button>
                    <Button size="sm" variant="secondary" disabled={note.trim().length < 5} isLoading={review.isPending}
                      onClick={() => review.mutate({ entryId, action: "needs_correction", comment: note.trim() }, { onSuccess: done, onError: (e) => fail(e, "Couldn't save it.") })}>Needs correction</Button>
                    {entry.review && entry.review.status !== "none" && <Button size="sm" variant="ghost" onClick={() => review.mutate({ entryId, action: "clear" }, { onSuccess: done })}>Clear mark</Button>}
                    <Button size="sm" variant="ghost" onClick={() => setMode("none")}>Cancel</Button>
                  </div>
                </div>
              )}

              {entry && <Card title="Details"><Details entry={entry} /></Card>}

              <Card title="Status timeline" aside={<span className="text-xs text-gray-500">{items.length} step{items.length === 1 ? "" : "s"}</span>}>
                <Timeline items={items} />
              </Card>

              <Card title="Comments" aside={<span className="text-xs text-gray-500">{comments.length}</span>}>
                {act?.comment && (
                  <form className="mb-3 flex flex-col gap-2" onSubmit={(e) => {
                    e.preventDefault();
                    const text = comment.trim();
                    if (!text) return;
                    addComment.mutate({ entryId, text }, { onSuccess: () => { setComment(""); setProblem(null); }, onError: (er) => fail(er, "Couldn't add the comment.") });
                  }}>
                    <label htmlFor="entry-comment" className="sr-only">Add a comment</label>
                    <textarea id="entry-comment" value={comment} onChange={(e) => setComment(e.target.value)} rows={2} maxLength={1000} placeholder="Add a comment…"
                      className="w-full resize-y rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-gray-900 shadow-xs outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-3 focus:ring-brand-500/15" />
                    <div className="flex justify-end"><Button type="submit" size="sm" variant="secondary" isLoading={addComment.isPending} disabled={!comment.trim()}>Add comment</Button></div>
                  </form>
                )}
                <ul className="flex flex-col gap-2.5">
                  {comments.map((c) => (
                    <li key={c.key} className={`rounded-xl px-3 py-2 text-sm ${c.mine ? "bg-brand-500/8 ring-1 ring-brand-500/20" : "bg-surface-subtle"}`}>
                      <p className="text-xs text-gray-500">
                        <span className="font-semibold text-gray-700">{c.mine ? c.actor.name ?? "Someone" : "System"}</span>
                        {c.mine && ` (${roleLabel(c.actor.role)})`} · {fmtMoment(c.at)}
                      </p>
                      <p className={`mt-0.5 break-words ${c.mine ? "text-gray-900" : "text-gray-700"}`}>{c.text}</p>
                    </li>
                  ))}
                  {comments.length === 0 && <li className="text-sm text-gray-500">No comments yet.</li>}
                </ul>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
