import { useMemo, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconAlertTriangle, IconCheckCircle, IconDownload } from "@/components/ui/icons";
import { usePartners } from "@/features/stores/useStores";
import { usePermission } from "@/hooks/usePermission";
import { pushToast } from "@/lib/toast";
import { complianceMonths, monthLabel } from "@/lib/months";
import {
  downloadDocsZip,
  openDocument,
  printDocuments,
  useClearBill,
  useComplianceSearch,
  useDueBills,
  type DocBrief,
  type SearchFilters,
} from "@/features/compliance/api";

const EMPTY: SearchFilters = { month: complianceMonths()[0], partner: "", entity: "", state: "", city: "", vendor: "", q: "", kind: "any" };
const field =
  "h-10 w-full rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

function DocPill({ doc, label }: { doc: DocBrief | null; label: string }) {
  if (!doc) return <span className="text-xs text-gray-400">No {label}</span>;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {label === "bill" ? (
        doc.status === "CLEARED" ? <Badge tone="success">Cleared</Badge> : <Badge tone={doc.overdue ? "danger" : "warning"}>{doc.overdue ? "Overdue" : "Pending"}</Badge>
      ) : (
        <Badge tone="success">Card</Badge>
      )}
      <button onClick={() => void openDocument(doc.id)} className="text-xs font-semibold text-brand-600 hover:text-brand-700">View</button>
    </div>
  );
}

export function AccountsPage() {
  const canClear = usePermission("accounts.clear");
  const { data: partners = [] } = usePartners();
  const due = useDueBills();
  const clear = useClearBill();

  const [draft, setDraft] = useState<SearchFilters>(EMPTY);
  const [applied, setApplied] = useState<SearchFilters>(EMPTY);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set()); // `${storeId}:${month}`
  const [busy, setBusy] = useState<"zip" | "print" | null>(null);
  const search = useComplianceSearch(applied, page);

  const rows = useMemo(() => search.data?.items ?? [], [search.data]);
  const rowKey = (r: { storeId: string; month: string }) => `${r.storeId}:${r.month}`;
  const allOnPageSelected = rows.length > 0 && rows.every((r) => selected.has(rowKey(r)));

  // documents behind the selected rows, honouring the Card / Bill / Both filter
  const selectedDocIds = useMemo(() => {
    const ids: string[] = [];
    rows.filter((r) => selected.has(rowKey(r))).forEach((r) => {
      if (r.card && applied.kind !== "bill") ids.push(r.card.id);
      if (r.bill && applied.kind !== "card") ids.push(r.bill.id);
    });
    return ids;
  }, [rows, selected, applied.kind]);

  function submit(e: FormEvent) {
    e.preventDefault();
    setApplied(draft);
    setPage(1);
    setSelected(new Set());
  }

  function togglePage() {
    setSelected((prev) => {
      const next = new Set(prev);
      rows.forEach((r) => (allOnPageSelected ? next.delete(rowKey(r)) : next.add(rowKey(r))));
      return next;
    });
  }

  async function run(kind: "zip" | "print" | "view") {
    if (selectedDocIds.length === 0) return;
    if (kind === "view") {
      selectedDocIds.slice(0, 5).forEach((id) => void openDocument(id));
      if (selectedDocIds.length > 5) pushToast("Opened the first 5 — use Download for the rest.", "info");
      return;
    }
    setBusy(kind);
    try {
      if (kind === "zip") await downloadDocsZip(selectedDocIds);
      else {
        const r = await printDocuments(selectedDocIds);
        if (r.opened) pushToast(`${r.opened} PDF${r.opened > 1 ? "s" : ""} opened in new tabs — print them from there.`, "info");
      }
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Accounts" subtitle="Bill due alerts, and every card and bill on file — search, view, print or download." />

      {/* Due alerts */}
      <section className="rounded-xl border border-surface-border bg-white shadow-card">
        <header className="flex items-center justify-between gap-3 border-b border-surface-border/80 px-5 py-4">
          <h3 className="flex items-center gap-2 text-sm font-bold text-gray-900">
            <IconAlertTriangle className="h-4 w-4 text-status-warning" /> Bills due
            {due.data && due.data.total > 0 && <Badge tone="danger">{due.data.total}</Badge>}
          </h3>
          <span className="text-xs text-gray-400">Pending bills whose due date has arrived · most overdue first</span>
        </header>
        <div className="p-5">
          {due.isLoading && <Skeleton className="h-24" />}
          {due.isError && <ErrorState message="Couldn't load due bills." onRetry={() => due.refetch()} />}
          {due.data && due.data.items.length === 0 && (
            <p className="flex items-center gap-2 text-sm font-medium text-status-success">
              <IconCheckCircle className="h-5 w-5" /> No bills are due right now.
            </p>
          )}
          {due.data && due.data.items.length > 0 && (
            <ul className="flex max-h-96 flex-col divide-y divide-surface-border overflow-auto">
              {due.data.items.map((b) => (
                <li key={b.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-gray-900">{b.storeName}</p>
                    <p className="text-xs text-gray-500">
                      {[b.externalCode, b.platform, b.entity, b.state, b.vendorName].filter(Boolean).join(" · ")} · {monthLabel(b.month)}
                    </p>
                  </div>
                  <Badge tone={b.daysOverdue > 30 ? "danger" : "warning"}>
                    {b.daysOverdue === 0 ? "due today" : `${b.daysOverdue} day${b.daysOverdue > 1 ? "s" : ""} overdue`}
                  </Badge>
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => void openDocument(b.id)}>View</Button>
                    {canClear && (
                      <Button size="sm" isLoading={clear.isPending && clear.variables === b.id} onClick={() => clear.mutate(b.id)}>
                        Mark cleared
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* Search */}
      <form onSubmit={submit} className="grid gap-3 rounded-xl border border-surface-border bg-white p-4 shadow-card sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Month
          <select className={field} value={draft.month} onChange={(e) => setDraft({ ...draft, month: e.target.value })}>
            {complianceMonths().map((m) => (
              <option key={m} value={m}>{monthLabel(m)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Platform
          <select className={field} value={draft.partner} onChange={(e) => setDraft({ ...draft, partner: e.target.value })}>
            <option value="">All platforms</option>
            {partners.map((p) => (
              <option key={p.slug} value={p.slug}>{p.name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Document
          <select className={field} value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as SearchFilters["kind"] })}>
            <option value="any">Card or bill</option>
            <option value="card">Card only</option>
            <option value="bill">Bill only</option>
            <option value="both">Both on file</option>
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Store
          <input className={field} value={draft.q} onChange={(e) => setDraft({ ...draft, q: e.target.value })} placeholder="Name or code" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Entity
          <input className={field} value={draft.entity} onChange={(e) => setDraft({ ...draft, entity: e.target.value })} placeholder="e.g. BCPL" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          State
          <input className={field} value={draft.state} onChange={(e) => setDraft({ ...draft, state: e.target.value })} placeholder="e.g. Delhi" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          City
          <input className={field} value={draft.city} onChange={(e) => setDraft({ ...draft, city: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Vendor
          <input className={field} value={draft.vendor} onChange={(e) => setDraft({ ...draft, vendor: e.target.value })} />
        </label>
        <div className="flex gap-2 sm:col-span-2 lg:col-span-4">
          <Button type="submit">Search</Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setDraft(EMPTY);
              setApplied(EMPTY);
              setPage(1);
              setSelected(new Set());
            }}
          >
            Reset
          </Button>
        </div>
      </form>

      {/* Selection actions */}
      {selected.size > 0 && (
        <div className="sticky top-[5rem] z-10 flex flex-wrap items-center gap-3 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 shadow-md">
          <span className="text-sm font-semibold text-brand-800">
            {selected.size} store{selected.size > 1 ? "s" : ""} selected · {selectedDocIds.length} document{selectedDocIds.length === 1 ? "" : "s"}
          </span>
          <div className="ml-auto flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" disabled={!selectedDocIds.length} onClick={() => void run("view")}>View</Button>
            <Button size="sm" variant="secondary" disabled={!selectedDocIds.length} isLoading={busy === "print"} onClick={() => void run("print")}>Print</Button>
            <Button size="sm" disabled={!selectedDocIds.length} isLoading={busy === "zip"} onClick={() => void run("zip")}>
              <IconDownload className="h-3.5 w-3.5" /> Download zip
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
          </div>
        </div>
      )}

      {search.isLoading && <Skeleton className="h-56" />}
      {search.isError && <ErrorState message="Couldn't search documents." onRetry={() => search.refetch()} />}
      {search.data && rows.length === 0 && <EmptyState title="No documents match" description="Change the month or filters and search again." />}

      {rows.length > 0 && (
        <>
          <p className="text-sm text-gray-500">{search.data?.total} store{search.data?.total === 1 ? "" : "s"} · {monthLabel(applied.month)}</p>
          <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-white shadow-card">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                  <th className="w-10 px-4 py-3">
                    <input type="checkbox" aria-label="Select all on this page" checked={allOnPageSelected} onChange={togglePage} className="accent-brand-500" />
                  </th>
                  <th className="px-3 py-3">Store</th>
                  <th className="px-3 py-3">Entity</th>
                  <th className="px-3 py-3">Location</th>
                  <th className="px-3 py-3">Vendor</th>
                  <th className="px-3 py-3">Card</th>
                  <th className="px-4 py-3">Bill</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={rowKey(r)} className="border-t border-surface-border/70 align-top">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.name}`}
                        checked={selected.has(rowKey(r))}
                        onChange={() =>
                          setSelected((prev) => {
                            const next = new Set(prev);
                            if (next.has(rowKey(r))) next.delete(rowKey(r));
                            else next.add(rowKey(r));
                            return next;
                          })
                        }
                        className="accent-brand-500"
                      />
                    </td>
                    <td className="px-3 py-3" data-label="Store">
                      <div className="font-medium text-gray-900">{r.name}</div>
                      <div className="text-xs text-gray-500">{[r.externalCode, r.platform].filter(Boolean).join(" · ")}</div>
                    </td>
                    <td className="px-3 py-3 text-gray-600" data-label="Entity">{r.entity ?? "—"}</td>
                    <td className="px-3 py-3 text-gray-600" data-label="Location">{[r.city, r.state].filter(Boolean).join(", ") || "—"}</td>
                    <td className="px-3 py-3 text-gray-600" data-label="Vendor">{r.vendorName ?? "—"}</td>
                    <td className="px-3 py-3" data-label="Card"><DocPill doc={r.card} label="card" /></td>
                    <td className="px-4 py-3" data-label="Bill"><DocPill doc={r.bill} label="bill" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {search.data && <Pagination page={search.data.page} pageSize={search.data.pageSize} total={search.data.total} onPageChange={setPage} />}
        </>
      )}
    </div>
  );
}
