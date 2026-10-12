import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { pushToast } from "@/lib/toast";
import { useVendorAuth } from "@/features/vendor/vendor-auth-context";
import { useTicket, useTickets, useVendorMutation } from "@/features/vendor/useVendorData";
import { Card, ErrorNote, ListSkeleton, PageNav, PhotoPicker, SectionTitle, StoreSelect, TicketStatusBadge } from "@/features/vendor/parts";
import { fmtDateTime, titleCase } from "@/features/vendor/format";
import { openVendorFile, vendorApi, type Attachment } from "@/features/vendor/vendorApi";

const FILTERS = [
  { label: "All", value: "" },
  { label: "Open", value: "OPEN" },
  { label: "In progress", value: "IN_PROGRESS" },
  { label: "Resolved", value: "RESOLVED" },
];

const CATEGORIES = [
  ["SHORT_SUPPLY", "Short supply"], ["LATE_DELIVERY", "Late delivery"], ["NO_DELIVERY", "No delivery"], ["DAMAGED", "Damaged bottles"],
  ["QUALITY", "Quality issue"], ["BILLING", "Billing"], ["OTHER", "Something else"],
] as const;

export function VendorTickets() {
  const isPoc = useVendorAuth().account?.kind === "poc";
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const q = useTickets({ status: status || undefined, page, page_size: 20 });
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-heading">Tickets</h1>
          <p className="text-sm text-gray-500">{isPoc ? "Problems raised for your stores." : "Problems your store POCs have raised."}</p>
        </div>
        {isPoc && <Link to="/vendor/tickets/new" className="shrink-0 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white">New</Link>}
      </div>

      <div className="mt-4 flex gap-1.5 overflow-x-auto pb-1" role="group" aria-label="Status">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={status === f.value}
            onClick={() => { setStatus(f.value); setPage(1); }}
            className={`h-9 shrink-0 rounded-full border px-3.5 text-sm font-semibold ${status === f.value ? "border-brand-600 bg-brand-50 text-brand-700" : "border-surface-border bg-surface text-gray-600"}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="mt-3">
        {q.isLoading ? (
          <ListSkeleton />
        ) : q.isError ? (
          <ErrorNote message={q.error.message} onRetry={() => q.refetch()} />
        ) : q.data!.items.length === 0 ? (
          <EmptyState title="No tickets" description={isPoc ? "Raise one if something is wrong with a delivery." : "When a POC raises a ticket for your stores it appears here."} />
        ) : (
          <div className="flex flex-col gap-2">
            {q.data!.items.map((t) => (
              <Link key={t.id} to={`/vendor/tickets/${t.id}`}>
                <Card className="!p-3 active:bg-surface-subtle">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-semibold text-gray-900">#{t.number} · {t.title}</p>
                    <TicketStatusBadge status={t.status} />
                  </div>
                  <p className="mt-1 truncate text-xs text-gray-500">{t.store_name} · {titleCase(t.category)} · {fmtDateTime(t.created_at)}</p>
                </Card>
              </Link>
            ))}
          </div>
        )}
        {q.data && <PageNav page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </div>
    </div>
  );
}

export function NewTicket() {
  const navigate = useNavigate();
  const isPoc = useVendorAuth().account?.kind === "poc";
  const [store, setStore] = useState("");
  const [category, setCategory] = useState<string>("SHORT_SUPPLY");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const raise = useVendorMutation((f: FormData) => vendorApi.raiseTicket(f), ["tickets", "notifications"]);

  if (!isPoc) return <Navigate to="/vendor/tickets" replace />;

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const f = new FormData();
    f.set("store_id", store);
    f.set("category", category);
    f.set("title", title.trim());
    if (description.trim()) f.set("description", description.trim());
    photos.forEach((p) => f.append("photos", p));
    raise.mutate(f, {
      onSuccess: (t) => { pushToast("Ticket raised. We will get back to you.", "success"); navigate(`/vendor/tickets/${t.id}`, { replace: true }); },
      onError: (err) => setError(err.message),
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold text-heading">Raise a ticket</h1>
        <p className="text-sm text-gray-500">Tell us what went wrong. Photos help us fix it faster.</p>
      </div>
      <StoreSelect value={store} onChange={setStore} />
      <label className="flex flex-col gap-1.5">
        <span className="text-[13px] font-semibold text-gray-700">What happened?</span>
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="h-11 rounded-lg border border-surface-border bg-surface px-3 text-sm">
          {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </label>
      <Input label="Short title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={160} placeholder="e.g. Only 40 of 100 bottles arrived" required />
      <label className="flex flex-col gap-1.5">
        <span className="text-[13px] font-semibold text-gray-700">Details <span className="font-normal text-gray-500">(optional)</span></span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} rows={4} className="rounded-lg border border-surface-border bg-surface px-3.5 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20" />
      </label>
      <PhotoPicker files={photos} onChange={setPhotos} />
      {error && <ErrorNote message={error} />}
      <Button type="submit" size="lg" fullWidth isLoading={raise.isPending} disabled={!store || title.trim().length < 3}>Send ticket</Button>
    </form>
  );
}

function Photos({ ticketId, items }: { ticketId: string; items: Attachment[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {items.map((a) => (
        <button
          key={a.id}
          type="button"
          onClick={() => openVendorFile(`/external/tickets/${ticketId}/attachments/${a.id}`).catch((e: Error) => pushToast(e.message))}
          className="rounded-md bg-surface-muted px-2.5 py-1.5 text-xs font-medium text-brand-700"
        >
          View photo
        </button>
      ))}
    </div>
  );
}

export function TicketDetailPage() {
  const { id = "" } = useParams();
  const isPoc = useVendorAuth().account?.kind === "poc";
  const q = useTicket(id);
  const [body, setBody] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const reply = useVendorMutation((f: FormData) => vendorApi.reply(id, f), ["ticket", "tickets"]);

  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.isError) return <ErrorNote message={q.error.message} onRetry={() => q.refetch()} />;
  const t = q.data!;
  const closed = t.status === "CLOSED";

  function send(e: FormEvent) {
    e.preventDefault();
    const f = new FormData();
    f.set("body", body.trim());
    photos.forEach((p) => f.append("photos", p));
    reply.mutate(f, {
      onSuccess: () => { setBody(""); setPhotos([]); },
      onError: (err) => pushToast(err.message),
    });
  }

  return (
    <div>
      <Link to="/vendor/tickets" className="text-sm font-semibold text-brand-600">← Tickets</Link>
      <div className="mt-2 flex items-start justify-between gap-2">
        <h1 className="text-lg font-bold text-heading">#{t.number} · {t.title}</h1>
        <TicketStatusBadge status={t.status} />
      </div>
      <p className="mt-1 text-xs text-gray-500">{t.store_name} · {titleCase(t.category)} · raised {fmtDateTime(t.created_at)}</p>
      {t.description && <Card className="mt-3 whitespace-pre-wrap !p-3 text-sm text-gray-800">{t.description}</Card>}
      <Photos ticketId={t.id} items={t.attachments.filter((a) => !a.comment_id)} />

      <SectionTitle>Conversation</SectionTitle>
      {t.comments.length === 0 && <p className="text-sm text-gray-500">No replies yet.</p>}
      <div className="flex flex-col gap-2">
        {t.comments.map((c) =>
          c.event ? (
            <p key={c.id} className="text-center text-xs text-gray-500">{c.body} · {fmtDateTime(c.created_at)}</p>
          ) : (
            <div key={c.id} className={`max-w-[88%] rounded-xl px-3 py-2 text-sm ${c.mine ? "ml-auto bg-brand-50 text-gray-900" : "bg-surface ring-1 ring-surface-border"}`}>
              <p className="mb-0.5 text-[11px] font-semibold text-gray-500">{c.mine ? "You" : "Veekay team"} · {fmtDateTime(c.created_at)}</p>
              <p className="whitespace-pre-wrap">{c.body}</p>
              <Photos ticketId={t.id} items={t.attachments.filter((a) => a.comment_id === c.id)} />
            </div>
          ),
        )}
      </div>

      {!isPoc ? (
        <p className="mt-5 rounded-xl bg-surface-muted px-3.5 py-3 text-sm text-gray-600">Your store POC handles replies on this ticket. You will get an alert when it changes.</p>
      ) : closed ? (
        <p className="mt-5 rounded-lg bg-surface-muted px-3 py-2.5 text-sm text-gray-600">This ticket is closed. <Link to="/vendor/tickets/new" className="font-semibold text-brand-600">Raise a new one</Link> if the problem is back.</p>
      ) : (
        <form onSubmit={send} className="mt-5 flex flex-col gap-3">
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} maxLength={2000} placeholder="Write a reply…" aria-label="Reply" className="rounded-lg border border-surface-border bg-surface px-3.5 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20" />
          <PhotoPicker files={photos} onChange={setPhotos} label="Add photos" />
          <Button type="submit" isLoading={reply.isPending} disabled={!body.trim()}>Send reply</Button>
        </form>
      )}
    </div>
  );
}
