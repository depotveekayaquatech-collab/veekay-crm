import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconSearch } from "@/components/ui/icons";
import { usePartners } from "@/features/stores/useStores";
import { usePermission } from "@/hooks/usePermission";
import {
  openDocument,
  useComplianceStores,
  useRemoveDoc,
  type ComplianceStoreRow,
  type DocBrief,
} from "@/features/compliance/api";
import { UploadDocsModal } from "@/features/compliance/UploadDocsModal";
import { monthLabel } from "@/lib/months";

type Target = { row: ComplianceStoreRow; kind: "card" | "bill" };

function BillBadge({ doc }: { doc: DocBrief }) {
  if (doc.status === "CLEARED") return <Badge tone="success">Cleared</Badge>;
  return <Badge tone={doc.overdue ? "danger" : "warning"}>{doc.overdue ? "Overdue" : "Pending"} · due {doc.dueDate}</Badge>;
}

function DocCell({
  doc,
  kind,
  onUpload,
  onRemove,
}: {
  doc: DocBrief | null;
  kind: "card" | "bill";
  onUpload: () => void;
  onRemove: () => void;
}) {
  if (!doc) {
    return (
      <Button size="sm" variant="secondary" onClick={onUpload}>
        Upload {kind}
      </Button>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {kind === "bill" ? <BillBadge doc={doc} /> : <Badge tone="success">Uploaded</Badge>}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs font-semibold">
        <button onClick={() => void openDocument(doc.id)} className="text-brand-600 hover:text-brand-700">View</button>
        <button onClick={onUpload} className="text-brand-600 hover:text-brand-700">Replace</button>
        <button onClick={onRemove} className="text-status-danger hover:opacity-80">Remove</button>
      </div>
    </div>
  );
}

export function CompliancePage() {
  const [params] = useSearchParams();
  const isAdmin = usePermission("compliance.manage");
  const { data: partners = [] } = usePartners();
  const [month, setMonth] = useState("");
  const [partner, setPartner] = useState("");
  const [q, setQ] = useState(params.get("q") ?? "");
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<Target | null>(null);
  const [removing, setRemoving] = useState<{ doc: DocBrief; name: string; kind: string } | null>(null);
  const remove = useRemoveDoc();

  const { data, isLoading, isError, refetch } = useComplianceStores({ month, partner, q, page });
  const activeMonth = month || data?.month || "";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Compliance"
        subtitle="Upload each store's compliance card and its monthly bill. Bills are due 45 days after the month ends."
      />

      {data && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { l: "Stores", v: data.total, t: "brand" },
            { l: "Cards uploaded", v: `${data.cardsDone} / ${data.total}`, t: "success" },
            { l: "Bills uploaded", v: `${data.billsDone} / ${data.total}`, t: "aqua" },
            { l: "Bills pending", v: data.billsPending, t: "warning" },
          ].map((k) => (
            <div key={k.l} className={`tile tile-${k.t} rounded-xl border border-surface-border bg-white p-5 shadow-card`}>
              <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{k.l}</p>
              <p className="mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums text-ink-900">{k.v}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Month
          <select
            value={activeMonth}
            onChange={(e) => {
              setMonth(e.target.value);
              setPage(1);
            }}
            className="h-10 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm"
          >
            {(data?.months ?? [activeMonth]).filter(Boolean).map((m) => (
              <option key={m} value={m}>{monthLabel(m)}</option>
            ))}
          </select>
        </label>
        {isAdmin && (
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Platform
            <select
              value={partner}
              onChange={(e) => {
                setPartner(e.target.value);
                setPage(1);
              }}
              className="h-10 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm"
            >
              <option value="">All platforms</option>
              {partners.map((p) => (
                <option key={p.slug} value={p.slug}>{p.name}</option>
              ))}
            </select>
          </label>
        )}
        <div className="relative ml-auto w-full sm:w-72">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="Search store name or code"
            aria-label="Search stores"
            className="h-10 w-full rounded-lg border border-surface-border bg-white pl-9 pr-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </div>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load your stores." onRetry={() => refetch()} />}
      {data && data.items.length === 0 && <EmptyState title="No stores found" description="Try a different month or search." />}

      {data && data.items.length > 0 && (
        <>
          <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-white shadow-card">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                  <th className="px-4 py-3">Store</th>
                  <th className="px-3 py-3">Location</th>
                  <th className="px-3 py-3">Vendor</th>
                  <th className="px-3 py-3">Compliance card</th>
                  <th className="px-4 py-3">Bill</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.storeId} className="border-t border-surface-border/70 align-top">
                    <td className="px-4 py-3" data-label="Store">
                      <div className="font-medium text-gray-900">{row.name}</div>
                      <div className="text-xs text-gray-500">{[row.externalCode, row.platform, row.entity].filter(Boolean).join(" · ")}</div>
                    </td>
                    <td className="px-3 py-3 text-gray-600" data-label="Location">{[row.city, row.state].filter(Boolean).join(", ") || "—"}</td>
                    <td className="px-3 py-3 text-gray-600" data-label="Vendor">{row.vendorName ?? "—"}</td>
                    <td className="px-3 py-3" data-label="Compliance card">
                      <DocCell
                        doc={row.card}
                        kind="card"
                        onUpload={() => setTarget({ row, kind: "card" })}
                        onRemove={() => row.card && setRemoving({ doc: row.card, name: row.name, kind: "card" })}
                      />
                    </td>
                    <td className="px-4 py-3" data-label="Bill">
                      <DocCell
                        doc={row.bill}
                        kind="bill"
                        onUpload={() => setTarget({ row, kind: "bill" })}
                        onRemove={() => row.bill && setRemoving({ doc: row.bill, name: row.name, kind: "bill" })}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={data.page} pageSize={data.pageSize} total={data.total} onPageChange={setPage} />
        </>
      )}

      {target && (
        <UploadDocsModal
          key={`${target.row.storeId}-${target.kind}`}
          storeId={target.row.storeId}
          storeName={target.row.name}
          month={activeMonth}
          monthLabel={monthLabel(activeMonth)}
          kind={target.kind}
          replacing={Boolean(target.kind === "card" ? target.row.card : target.row.bill)}
          onClose={() => setTarget(null)}
        />
      )}

      <Modal
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title={`Remove ${removing?.kind ?? "document"}?`}
        description={removing ? `${removing.name} · ${monthLabel(activeMonth)}` : undefined}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRemoving(null)}>Keep it</Button>
            <Button
              variant="danger"
              isLoading={remove.isPending}
              onClick={() => removing && remove.mutate(removing.doc.id, { onSuccess: () => setRemoving(null) })}
            >
              Remove
            </Button>
          </>
        }
      >
        <p className="text-sm text-gray-600">The file is deleted and this can&apos;t be undone. You can upload a new one afterwards.</p>
      </Modal>
    </div>
  );
}
