import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { daysAgo } from "@/lib/dates";
import { pushToast } from "@/lib/toast";
import { useVendorAuth } from "@/features/vendor/vendor-auth-context";
import { useDeliveries, useVendorMutation } from "@/features/vendor/useVendorData";
import { Card, ErrorNote, ListSkeleton, OutcomeBadge, PageNav, PhotoPicker, StoreSelect } from "@/features/vendor/parts";
import { fmtDate } from "@/features/vendor/format";
import { vendorApi, type Outcome } from "@/features/vendor/vendorApi";

const OUTCOMES: { value: Outcome; label: string; hint: string }[] = [
  { value: "RECEIVED", label: "All received", hint: "Everything arrived fine" },
  { value: "SHORT", label: "Short", hint: "Fewer bottles than expected" },
  { value: "DAMAGED", label: "Damaged", hint: "Bottles arrived damaged" },
];

export function VendorDeliveries() {
  const isPoc = useVendorAuth().account?.kind === "poc";
  const [page, setPage] = useState(1);
  const q = useDeliveries({ page, page_size: 30 });
  return (
    <div>
      <Link to="/vendor" className="text-sm font-semibold text-brand-600">← Home</Link>
      <div className="mt-2 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-heading">Deliveries</h1>
          <p className="text-sm text-gray-500">{isPoc ? "Confirmed or reported at your stores." : "What your store POCs have confirmed or reported."}</p>
        </div>
        {isPoc && <Link to="/vendor/deliveries/new" className="shrink-0 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white">Confirm</Link>}
      </div>
      <div className="mt-4">
        {q.isLoading ? (
          <ListSkeleton />
        ) : q.isError ? (
          <ErrorNote message={q.error.message} onRetry={() => q.refetch()} />
        ) : q.data!.items.length === 0 ? (
          <EmptyState title="Nothing confirmed yet" description={isPoc ? "Confirm a delivery, or flag one that came short or damaged." : "Deliveries your POCs confirm or flag will show here."} />
        ) : (
          <div className="flex flex-col gap-2">
            {q.data!.items.map((d) => (
              <Card key={d.id} className="!p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-gray-900">{fmtDate(d.delivery_date)}</p>
                  <OutcomeBadge outcome={d.outcome} />
                </div>
                <p className="mt-0.5 truncate text-xs text-gray-500">{d.store_name} · {d.reported_by}</p>
                {d.expected_qty !== null && d.received_qty !== null && <p className="mt-1 text-xs text-gray-700">Expected {d.expected_qty}, received {d.received_qty}</p>}
                {d.note && <p className="mt-1 text-sm text-gray-700">{d.note}</p>}
                {d.ticket_id && <Link to={`/vendor/tickets/${d.ticket_id}`} className="mt-2 inline-block text-sm font-semibold text-brand-600">View ticket</Link>}
              </Card>
            ))}
          </div>
        )}
        {q.data && <PageNav page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </div>
    </div>
  );
}

export function ConfirmDelivery() {
  const navigate = useNavigate();
  const isPoc = useVendorAuth().account?.kind === "poc";
  const [store, setStore] = useState("");
  const [date, setDate] = useState(daysAgo(0));
  const [outcome, setOutcome] = useState<Outcome>("RECEIVED");
  const [expected, setExpected] = useState("");
  const [received, setReceived] = useState("");
  const [note, setNote] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const confirm = useVendorMutation((f: FormData) => vendorApi.confirmDelivery(f), ["deliveries", "tickets"]);
  const problem = outcome !== "RECEIVED";
  if (!isPoc) return <Navigate to="/vendor/deliveries" replace />;

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const f = new FormData();
    f.set("store_id", store);
    f.set("delivery_date", date);
    f.set("outcome", outcome);
    if (problem) {
      if (expected) f.set("expected_qty", expected);
      if (received) f.set("received_qty", received);
      if (note.trim()) f.set("note", note.trim());
      photos.forEach((p) => f.append("photos", p));
    }
    confirm.mutate(f, {
      onSuccess: (d) => {
        pushToast(d.ticket_id ? "Reported. A ticket was opened for our team." : "Delivery confirmed. Thank you.", "success");
        navigate("/vendor/deliveries", { replace: true });
      },
      onError: (err) => setError(err.message),
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold text-heading">Confirm a delivery</h1>
        <p className="text-sm text-gray-500">Once per store per day. Short or damaged deliveries open a ticket for our team.</p>
      </div>
      <StoreSelect value={store} onChange={setStore} />
      <Input label="Delivery date" type="date" value={date} min={daysAgo(14)} max={daysAgo(0)} onChange={(e) => setDate(e.target.value)} required />

      <div className="flex flex-col gap-1.5" role="radiogroup" aria-label="How did it go?">
        <span className="text-[13px] font-semibold text-gray-700">How did it go?</span>
        {OUTCOMES.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={outcome === o.value}
            onClick={() => setOutcome(o.value)}
            className={`rounded-lg border px-3.5 py-2.5 text-left ${outcome === o.value ? "border-brand-600 bg-brand-50" : "border-surface-border bg-surface"}`}
          >
            <span className="block text-sm font-semibold text-gray-900">{o.label}</span>
            <span className="block text-xs text-gray-500">{o.hint}</span>
          </button>
        ))}
      </div>

      {problem && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Expected" type="number" inputMode="numeric" min={0} value={expected} onChange={(e) => setExpected(e.target.value)} />
            <Input label="Received" type="number" inputMode="numeric" min={0} value={received} onChange={(e) => setReceived(e.target.value)} />
          </div>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold text-gray-700">What was wrong?</span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={1000} className="rounded-lg border border-surface-border bg-surface px-3.5 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20" />
          </label>
          <PhotoPicker files={photos} onChange={setPhotos} />
        </>
      )}
      {error && <ErrorNote message={error} />}
      <Button type="submit" size="lg" fullWidth isLoading={confirm.isPending} disabled={!store || !date || (problem && !note.trim() && !received)}>
        {problem ? "Report problem" : "Confirm delivery"}
      </Button>
    </form>
  );
}
