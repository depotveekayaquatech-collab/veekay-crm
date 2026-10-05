import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconMapPin } from "@/components/ui/icons";
import { CategoryBadge, PriorityBadge, StatusBadge } from "@/features/tickets/parts";
import { dueLabel, timeAgo } from "@/lib/ticketTime";
import { useTicket, useTicketMutations } from "@/features/tickets/useTickets";
import { PRIORITY_LABEL, STATUS_ACTION, TICKET_CODE, type TicketPriority } from "@/types/ticket";

const PRIORITIES = Object.entries(PRIORITY_LABEL).map(([value, label]) => ({ value, label }));

function Phone({ value }: { value: string | null }) {
  if (!value) return null;
  return (
    <a href={`tel:${value}`} className="font-medium text-brand-600 hover:text-brand-700">
      {value}
    </a>
  );
}

export function TicketDetailModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: t, isLoading, isError, refetch } = useTicket(id);
  const { update, comment } = useTicketMutations();
  const [text, setText] = useState("");
  const busy = update.isPending || comment.isPending;

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    await comment.mutateAsync({ id, body: text.trim() });
    setText("");
  }

  const due = t && t.status !== "RESOLVED" && t.status !== "CLOSED" ? dueLabel(t.dueAt) : null;

  return (
    <Modal open onClose={onClose} size="lg" title={t ? `${TICKET_CODE(t.number)} · ${t.title}` : "Ticket"}>
      {isLoading && <Skeleton className="h-72" />}
      {isError && <ErrorState message="Couldn't load this ticket." onRetry={() => refetch()} />}
      {t && (
        <div className="grid gap-6 md:grid-cols-[1fr_16rem]">
          <div className="flex min-w-0 flex-col gap-5">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={t.status} />
              <PriorityBadge priority={t.priority} />
              <CategoryBadge category={t.category} />
              {t.isOverdue && <Badge tone="danger">Overdue</Badge>}
            </div>

            {t.description ? (
              <p className="whitespace-pre-wrap rounded-lg bg-surface-subtle px-4 py-3 text-sm text-gray-700">{t.description}</p>
            ) : (
              <p className="text-sm text-gray-400">No extra details were added.</p>
            )}

            <div>
              <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-400">Activity</h4>
              <ol className="flex flex-col gap-3">
                <li className="text-xs text-gray-500">
                  Raised by <span className="font-semibold text-gray-700">{t.createdByName ?? "someone"}</span>{t.source === "google" ? " via Google" : ""} · {timeAgo(t.createdAt)}
                </li>
                {t.comments.map((c) =>
                  c.event ? (
                    <li key={c.id} className="flex items-center gap-2 text-xs text-gray-500">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-gray-300" />
                      <span>
                        <span className="font-semibold text-gray-700">{c.authorName ?? "Someone"}</span> · {c.body} · {timeAgo(c.createdAt)}
                      </span>
                    </li>
                  ) : (
                    <li key={c.id} className="rounded-lg border border-surface-border bg-surface px-3.5 py-2.5">
                      <p className="text-xs text-gray-500">
                        <span className="font-semibold text-gray-800">{c.authorName ?? "Someone"}</span> · {timeAgo(c.createdAt)}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-gray-800">{c.body}</p>
                    </li>
                  ),
                )}
              </ol>
            </div>

            <form onSubmit={send} className="flex flex-col gap-2">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="Write an update…"
                aria-label="Add a comment"
                className="rounded-md border border-surface-border bg-surface px-3 py-2 text-sm shadow-sm outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
              />
              <div className="flex justify-end">
                <Button type="submit" size="sm" isLoading={comment.isPending} disabled={!text.trim()}>Post update</Button>
              </div>
            </form>
          </div>

          <aside className="flex flex-col gap-4 text-sm">
            {t.nextStatuses.length > 0 && (
              <div className="flex flex-col gap-2">
                {t.nextStatuses.map((s, i) => (
                  <Button
                    key={s}
                    size="sm"
                    variant={i === 0 && s !== "OPEN" ? "primary" : "secondary"}
                    disabled={busy}
                    isLoading={update.isPending && update.variables?.status === s}
                    onClick={() => update.mutate({ id, status: s })}
                  >
                    {STATUS_ACTION[s]}
                  </Button>
                ))}
              </div>
            )}

            <dl className="flex flex-col gap-3 rounded-lg border border-surface-border p-3.5">
              <div>
                <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Store</dt>
                <dd className="mt-0.5 font-semibold text-gray-900">{t.store.name}</dd>
                <dd className="text-xs text-gray-500">{t.store.code} · {t.store.platformName}</dd>
                <dd className="mt-0.5 flex items-center gap-1 text-xs text-gray-500">
                  <IconMapPin className="h-3 w-3" />
                  {[t.store.city, t.store.state].filter(Boolean).join(", ") || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Region</dt>
                <dd className="mt-0.5 text-gray-900">{t.store.regionName ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Vendor</dt>
                <dd className="mt-0.5 text-gray-900">{t.store.vendorName ?? "—"} <Phone value={t.store.vendorNumber} /></dd>
              </div>
              {due && (
                <div>
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Deadline</dt>
                  <dd className={`mt-0.5 font-semibold ${due.late ? "text-status-danger" : "text-gray-900"}`}>{due.text}</dd>
                </div>
              )}
              {!t.canAssign && (
                <div>
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Assigned to</dt>
                  <dd className="mt-0.5 text-gray-900">{t.assignedToName ?? "Unassigned"}</dd>
                </div>
              )}
            </dl>

            {t.canSetPriority && (
              <Select
                label="Priority"
                value={t.priority}
                onChange={(e) => update.mutate({ id, priority: e.target.value as TicketPriority })}
                options={PRIORITIES}
                disabled={busy}
              />
            )}
            {t.canAssign && (
              <Select
                label="Assigned to"
                value={t.assignedToId ?? ""}
                onChange={(e) => (e.target.value ? update.mutate({ id, assignedToId: e.target.value }) : update.mutate({ id, unassign: true }))}
                placeholder="Unassigned"
                options={t.assignees.map((a) => ({ value: a.id, label: `${a.name} (${a.code})` }))}
                disabled={busy}
              />
            )}
          </aside>
        </div>
      )}
    </Modal>
  );
}
