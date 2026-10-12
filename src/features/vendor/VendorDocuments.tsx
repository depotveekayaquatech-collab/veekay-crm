import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { daysAgo } from "@/lib/dates";
import { pushToast } from "@/lib/toast";
import { useDocuments, useVendorMutation } from "@/features/vendor/useVendorData";
import { Card, ErrorNote, ListSkeleton, PageNav, PhotoPicker, StoreSelect } from "@/features/vendor/parts";
import { fmtDate, fmtMonth, fmtSize, recentMonths } from "@/features/vendor/format";
import { openVendorFile, vendorApi, type DocumentRow } from "@/features/vendor/vendorApi";

const KINDS = [
  { label: "All", value: "" },
  { label: "Cards", value: "card" },
  { label: "Bills", value: "bill" },
  { label: "Payments", value: "payment" },
];
const KIND_NAME = { card: "Compliance card", bill: "Bill", payment: "Payment proof" } as const;

function BillState({ d }: { d: DocumentRow }) {
  if (d.kind !== "bill" || !d.status) return null;
  if (d.status === "CLEARED") return <Badge tone="success">Cleared</Badge>;
  const late = d.due_date && d.due_date <= daysAgo(0);
  return <Badge tone={late ? "danger" : "warning"}>{late ? "Overdue" : "Due"} {d.due_date ? fmtDate(d.due_date) : ""}</Badge>;
}

export function VendorDocuments() {
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "";
  const [store, setStore] = useState("");
  const [page, setPage] = useState(1);
  const q = useDocuments({ kind: kind || undefined, store_id: store || undefined, page, page_size: 30 });

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-heading">Documents</h1>
          <p className="text-sm text-gray-500">Cards, bills and payment proofs.</p>
        </div>
        <Link to="/vendor/documents/upload" className="shrink-0 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-semibold text-white">Upload</Link>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        <div className="flex gap-1.5 overflow-x-auto pb-1" role="group" aria-label="Type">
          {KINDS.map((k) => (
            <button
              key={k.value}
              type="button"
              aria-pressed={kind === k.value}
              onClick={() => { setParams(k.value ? { kind: k.value } : {}, { replace: true }); setPage(1); }}
              className={`h-9 shrink-0 rounded-full border px-3.5 text-sm font-semibold ${kind === k.value ? "border-brand-600 bg-brand-50 text-brand-700" : "border-surface-border bg-surface text-gray-600"}`}
            >
              {k.label}
            </button>
          ))}
        </div>
        <StoreSelect value={store} onChange={(v) => { setStore(v); setPage(1); }} allLabel="All my stores" />
      </div>

      <div className="mt-4">
        {q.isLoading ? (
          <ListSkeleton />
        ) : q.isError ? (
          <ErrorNote message={q.error.message} onRetry={() => q.refetch()} />
        ) : q.data!.items.length === 0 ? (
          <EmptyState title="No documents" description="Upload a compliance card or payment proof to see it here." />
        ) : (
          <div className="flex flex-col gap-2">
            {q.data!.items.map((d) => (
              <Card key={d.id} className="!p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-gray-900">{KIND_NAME[d.kind]} · {fmtMonth(d.month)}</p>
                  <BillState d={d} />
                </div>
                <p className="mt-0.5 truncate text-xs text-gray-500">{d.store_name} · {fmtSize(d.size_bytes)}</p>
                <button
                  type="button"
                  onClick={() => openVendorFile(`/external/documents/${d.id}/file`).catch((e: Error) => pushToast(e.message))}
                  className="mt-2 text-sm font-semibold text-brand-600"
                >
                  Open file
                </button>
              </Card>
            ))}
          </div>
        )}
        {q.data && <PageNav page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </div>
    </div>
  );
}

export function UploadDocument() {
  const navigate = useNavigate();
  const months = recentMonths(12);
  const [store, setStore] = useState("");
  const [kind, setKind] = useState<"card" | "payment">("payment");
  const [month, setMonth] = useState(months[0].value);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const upload = useVendorMutation((f: FormData) => vendorApi.uploadDocument(f), ["documents"]);

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const f = new FormData();
    f.set("store_id", store);
    f.set("kind", kind);
    f.set("month", month);
    files.forEach((p) => f.append("files", p));
    upload.mutate(f, {
      onSuccess: () => { pushToast("Uploaded.", "success"); navigate("/vendor/documents", { replace: true }); },
      onError: (err) => setError(err.message),
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold text-heading">Upload a document</h1>
        <p className="text-sm text-gray-500">Several photos are joined into one PDF. Uploading again replaces the current file; the older one is kept on record.</p>
      </div>
      <StoreSelect value={store} onChange={setStore} />
      <div className="flex gap-2" role="group" aria-label="Type">
        {([["payment", "Payment proof"], ["card", "Compliance card"]] as const).map(([v, l]) => (
          <button
            key={v}
            type="button"
            aria-pressed={kind === v}
            onClick={() => setKind(v)}
            className={`h-11 flex-1 rounded-lg border text-sm font-semibold ${kind === v ? "border-brand-600 bg-brand-50 text-brand-700" : "border-surface-border bg-surface text-gray-600"}`}
          >
            {l}
          </button>
        ))}
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="text-[13px] font-semibold text-gray-700">Month</span>
        <select value={month} onChange={(e) => setMonth(e.target.value)} className="h-11 rounded-lg border border-surface-border bg-surface px-3 text-sm">
          {months.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </label>
      <PhotoPicker files={files} onChange={setFiles} max={10} accept="image/*,application/pdf" label="Photos or a PDF" />
      {error && <ErrorNote message={error} />}
      <Button type="submit" size="lg" fullWidth isLoading={upload.isPending} disabled={!store || files.length === 0}>Upload</Button>
    </form>
  );
}
