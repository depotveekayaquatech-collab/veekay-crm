import { SelectField } from "@/components/ui/Dropdown";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconDownload, IconSearch, IconUpload } from "@/components/ui/icons";
import { usePartners } from "@/features/stores/useStores";
import {
  DOC_LABEL,
  openDocument,
  openSummaryPdf,
  useComplianceRepo,
  useRemoveDoc,
  type ComplianceRow,
  type ComplianceStatus,
  type DocBrief,
  type DocKind,
  type RepoFilters,
} from "@/features/compliance/api";
import { BulkUploadModal } from "@/features/compliance/BulkUploadModal";
import { UploadDocsModal } from "@/features/compliance/UploadDocsModal";
import { monthLabel } from "@/lib/months";

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

const EMPTY: Omit<RepoFilters, "month"> = {
  partner: "", region: "", city: "", manager: "", missing: "", range: "", status: "", q: "", sort: "name", dir: "asc", page: 1,
};

const select =
  "h-10 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";
const label = "flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500";

const STATUS_TONE: Record<ComplianceStatus, "danger" | "warning" | "success"> = { PENDING: "danger", PARTIAL: "warning", COMPLETE: "success" };

/* ------------------------------- KPI tiles ------------------------------- */

function Tile({
  title, value, tone, active, onClick, hint,
}: {
  title: string; value: string | number; tone: "brand" | "aqua" | "success" | "warning" | "danger"; active?: boolean; onClick?: () => void; hint?: string;
}) {
  const text = tone === "danger" ? "text-status-danger" : tone === "success" ? "text-status-success" : tone === "warning" ? "text-status-warning" : tone === "aqua" ? "text-aqua-600" : "text-brand-600";
  const accent = tone === "danger" ? "warning" : tone;
  const body = (
    <>
      <p className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-gray-500">
        {title}
      </p>
      <p className={`mt-1.5 text-[1.6rem] font-bold leading-none tabular-nums ${text}`}>{value}</p>
      {hint && <p className="mt-1 text-[11px] text-gray-400">{hint}</p>}
    </>
  );
  const cls = `tile tile-${accent} rounded-xl border bg-surface p-4 text-left shadow-card transition-all duration-150 ${
    active ? "border-brand-300 ring-2 ring-brand-500/20" : "border-surface-border"
  } ${onClick ? "hover:-translate-y-0.5 hover:shadow-md" : ""}`;
  return onClick ? (
    <button onClick={onClick} className={cls}>{body}</button>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/* ------------------------------ table pieces ------------------------------ */

function Th({
  children, sortKey, f, onSort, className = "",
}: {
  children: React.ReactNode; sortKey?: string; f: RepoFilters; onSort: (k: string) => void; className?: string;
}) {
  const active = sortKey && f.sort === sortKey;
  return (
    <th className={`px-3 py-3 text-left text-[11px] font-bold uppercase tracking-wider ${className}`}>
      {sortKey ? (
        <button onClick={() => onSort(sortKey)} className={`inline-flex items-center gap-1 uppercase tracking-wider ${active ? "text-brand-700" : "text-gray-500 hover:text-gray-800"}`}>
          {children}
          <span className="text-[10px]">{active ? (f.dir === "asc" ? "▲" : "▼") : "↕"}</span>
        </button>
      ) : (
        <span className="text-gray-500">{children}</span>
      )}
    </th>
  );
}

function DocCell({
  doc, kind, onAdd, onRemove,
}: {
  doc: DocBrief | null; kind: DocKind; onAdd: () => void; onRemove: () => void;
}) {
  if (!doc) {
    return (
      <button
        onClick={onAdd}
        className="inline-flex items-center gap-1 rounded-md border border-dashed border-surface-border px-2 py-1 text-[11px] font-semibold text-gray-500 transition-colors hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700"
      >
        <span className="text-sm leading-none">+</span> Add {kind === "bill" ? "invoice" : kind === "payment" ? "proof" : "card"}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      {kind === "bill" ? (
        doc.status === "CLEARED" ? <Badge tone="success">Cleared</Badge> : <Badge tone={doc.overdue ? "danger" : "warning"}>{doc.overdue ? "Overdue" : "Pending"}</Badge>
      ) : (
        <Badge tone="success">{kind === "payment" ? "Paid" : "On file"}</Badge>
      )}
      <div className="flex gap-2 text-[11px] font-semibold">
        <button onClick={() => void openDocument(doc.id)} className="text-brand-600 hover:text-brand-700">View</button>
        <button onClick={onAdd} className="text-brand-600 hover:text-brand-700">Upload new</button>
        <button onClick={onRemove} className="text-status-danger hover:opacity-80">Remove</button>
      </div>
    </div>
  );
}

/* ---------------------------------- page ---------------------------------- */

export function CompliancePage() {
  const [params] = useSearchParams();
  const { data: partners = [] } = usePartners();
  const [f, setF] = useState<RepoFilters>({ month: "", ...EMPTY, q: params.get("q") ?? "" });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState<{ row: ComplianceRow; kind: DocKind } | null>(null);
  const [removing, setRemoving] = useState<{ doc: DocBrief; name: string; kind: DocKind } | null>(null);
  const [bulk, setBulk] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const remove = useRemoveDoc();

  const { data, isLoading, isError, refetch, isFetching } = useComplianceRepo(f);
  const month = f.month || data?.month || "";
  const set = (patch: Partial<RepoFilters>) => setF((p) => ({ ...p, page: 1, ...patch }));

  // month + year selects are two views of the single YYYY-MM filter
  const years = useMemo(() => [...new Set((data?.months ?? []).map((m) => m.slice(0, 4)))], [data?.months]);
  const year = month.slice(0, 4);
  const monthsInYear = (data?.months ?? []).filter((m) => m.startsWith(year));
  const pickYear = (y: string) => {
    const options = (data?.months ?? []).filter((m) => m.startsWith(y));
    set({ month: options.includes(`${y}-${month.slice(5)}`) ? `${y}-${month.slice(5)}` : (options[0] ?? month) });
  };

  const k = data?.kpis;

  const filtersActive = Object.entries(EMPTY).some(([key, v]) => !["sort", "dir", "page"].includes(key) && f[key as keyof RepoFilters] !== v);

  function onSort(key: string) {
    setF((p) => ({ ...p, page: 1, sort: key, dir: p.sort === key && p.dir === "asc" ? "desc" : "asc" }));
  }

  const rows = data?.items ?? [];
  const allOnPage = rows.length > 0 && rows.every((r) => selected.has(r.storeId));
  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      rows.forEach((r) => (allOnPage ? next.delete(r.storeId) : next.add(r.storeId)));
      return next;
    });
  }

  async function generate() {
    setPdfBusy(true);
    try {
      await openSummaryPdf([...selected], month);
    } finally {
      setPdfBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Store compliance repository"
        subtitle="Each store needs three documents a month — the compliance card, the invoice and the payment proof."
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setBulk(true)}>
              <IconUpload className="h-4 w-4" />
              Bulk upload
            </Button>
            <Button onClick={() => void generate()} disabled={selected.size === 0} isLoading={pdfBusy}>
              <IconDownload className="h-4 w-4" />
              Generate PDF ({selected.size})
            </Button>
          </div>
        }
      />

      {/* KPI tiles */}
      {k && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Tile title="Total stores" value={k.total} tone="brand" />
          <Tile title="Card logged" value={k.cardLogged} tone="aqua" />
          <Tile title="Invoice logged" value={k.invoiceLogged} tone="brand" />
          <Tile title="Payment proof logged" value={k.paymentLogged} tone="success" />
        </div>
      )}

      {/* filters */}
      <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
          <label className={label}>
            Month
            <SelectField className={select} value={month.slice(5)} onChange={(e) => set({ month: `${year}-${e.target.value}` })}>
              {monthsInYear.map((m) => (
                <option key={m} value={m.slice(5)}>{MONTH_NAMES[Number(m.slice(5)) - 1]}</option>
              ))}
            </SelectField>
          </label>
          <label className={label}>
            Year
            <SelectField className={select} value={year} onChange={(e) => pickYear(e.target.value)}>
              {years.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </SelectField>
          </label>
          <label className={label}>
            Region
            <SelectField className={select} value={f.region} onChange={(e) => set({ region: e.target.value })}>
              <option value="">All regions</option>
              {data?.options.regions.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </SelectField>
          </label>
          <label className={label}>
            City
            <SelectField className={select} value={f.city} onChange={(e) => set({ city: e.target.value })}>
              <option value="">All cities</option>
              {data?.options.cities.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </SelectField>
          </label>
          <label className={label}>
            Channel
            <SelectField className={select} value={f.partner} onChange={(e) => set({ partner: e.target.value, region: "", city: "", manager: "" })}>
              <option value="">All channels</option>
              {partners.map((p) => (
                <option key={p.slug} value={p.slug}>{p.name}</option>
              ))}
            </SelectField>
          </label>
          <label className={label}>
            Missing documents
            <SelectField className={select} value={f.missing} onChange={(e) => set({ missing: e.target.value })}>
              <option value="">All stores</option>
              <option value="any">Anything missing</option>
              <option value="card">Missing card</option>
              <option value="bill">Missing invoice</option>
              <option value="payment">Missing payment proof</option>
            </SelectField>
          </label>
          <label className={label}>
            Compliance filter
            <SelectField className={select} value={f.range} onChange={(e) => set({ range: e.target.value })}>
              <option value="">All ranges</option>
              <option value="0-25">0% (nothing on file)</option>
              <option value="26-50">33% (1 of 3)</option>
              <option value="51-75">67% (2 of 3)</option>
              <option value="100">100% (complete)</option>
            </SelectField>
          </label>
          <label className={label}>
            Delivery manager
            <SelectField className={select} value={f.manager} onChange={(e) => set({ manager: e.target.value })}>
              <option value="">All delivery managers</option>
              {data?.options.hasUnassigned && <option value="__none__">Unassigned</option>}
              {data?.options.managers.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </SelectField>
          </label>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-[12rem_1fr_auto]">
          <label className={label}>
            Status
            <SelectField className={select} value={f.status} onChange={(e) => set({ status: e.target.value })}>
              <option value="">All status</option>
              <option value="pending">Pending (nothing logged)</option>
              <option value="partial">Partial</option>
              <option value="complete">Complete</option>
            </SelectField>
          </label>
          <label className={label}>
            Search store
            <span className="relative block">
              <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input className={`${select} pl-9`} value={f.q} onChange={(e) => set({ q: e.target.value })} placeholder="Filter by store name or code…" />
            </span>
          </label>
          <div className="flex items-end">
            <Button variant="secondary" disabled={!filtersActive} onClick={() => setF((p) => ({ month: p.month, ...EMPTY }))}>
              Reset
            </Button>
          </div>
        </div>
      </section>

      {isLoading && <Skeleton className="h-72" />}
      {isError && <ErrorState message="Couldn't load the repository." onRetry={() => refetch()} />}
      {data && data.items.length === 0 && <EmptyState title="No stores match" description="Change the filters or the month." />}

      {data && data.items.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-500">
            <span>
              {data.total} store{data.total === 1 ? "" : "s"} · {monthLabel(month)}
              {isFetching && <span className="ml-2 text-xs text-gray-400">updating…</span>}
            </span>
            {selected.size > 0 && (
              <span className="flex items-center gap-3">
                <b className="text-gray-800">{selected.size} selected</b>
                <button className="font-semibold text-brand-600 hover:text-brand-700" onClick={() => setSelected(new Set())}>Clear selection</button>
              </span>
            )}
          </div>
          <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
            <table className="w-full min-w-[980px] text-sm">
              <thead>
                <tr className="bg-surface-subtle">
                  <th className="w-10 px-4 py-3">
                    <input type="checkbox" aria-label="Select all on this page" checked={allOnPage} onChange={toggleAll} className="accent-brand-500" />
                  </th>
                  <Th sortKey="name" f={f} onSort={onSort}>Store name</Th>
                  <Th sortKey="city" f={f} onSort={onSort}>City</Th>
                  <Th sortKey="channel" f={f} onSort={onSort}>Channel</Th>
                  <Th sortKey="manager" f={f} onSort={onSort}>Delivery manager</Th>
                  <Th sortKey="status" f={f} onSort={onSort}>Status</Th>
                  <Th sortKey="card" f={f} onSort={onSort}>Compliance card</Th>
                  <Th sortKey="bill" f={f} onSort={onSort}>Invoice</Th>
                  <Th sortKey="payment" f={f} onSort={onSort}>Payment proof</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const cell = (kind: DocKind) => (
                    <DocCell
                      doc={row[kind]}
                      kind={kind}
                      onAdd={() => setTarget({ row, kind })}
                      onRemove={() => row[kind] && setRemoving({ doc: row[kind] as DocBrief, name: row.name, kind })}
                    />
                  );
                  return (
                    <tr
                      key={row.storeId}
                      className={`border-t border-surface-border/70 align-top ${row.status === "PENDING" ? "bg-status-danger-soft/25" : ""} ${selected.has(row.storeId) ? "bg-brand-50/60" : ""}`}
                    >
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          aria-label={`Select ${row.name}`}
                          checked={selected.has(row.storeId)}
                          onChange={() =>
                            setSelected((prev) => {
                              const next = new Set(prev);
                              if (next.has(row.storeId)) next.delete(row.storeId);
                              else next.add(row.storeId);
                              return next;
                            })
                          }
                          className="accent-brand-500"
                        />
                      </td>
                      <td className="max-w-[16rem] px-3 py-3" data-label="Store">
                        <div className="font-medium text-gray-900" title={row.name}>{row.name}</div>
                        <div className="truncate text-[11px] text-gray-500">ID: {row.externalCode}</div>
                      </td>
                      <td className="px-3 py-3 text-gray-700" data-label="City">{row.city ?? "—"}</td>
                      <td className="px-3 py-3" data-label="Channel">{row.platform ? <Badge tone="info">{row.platform}</Badge> : "—"}</td>
                      <td className="px-3 py-3" data-label="Delivery manager">
                        {row.manager ?? <span className="rounded-md bg-surface-muted px-2 py-0.5 text-xs text-gray-500">Unassigned</span>}
                      </td>
                      <td className="px-3 py-3" data-label="Status">
                        <Badge tone={STATUS_TONE[row.status]}>{row.status}</Badge>
                        <div className="mt-1 text-[11px] tabular-nums text-gray-500">{row.percent}%</div>
                      </td>
                      <td className="px-3 py-3" data-label="Compliance card">{cell("card")}</td>
                      <td className="px-3 py-3" data-label="Invoice">{cell("bill")}</td>
                      <td className="px-3 py-3" data-label="Payment proof">{cell("payment")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pagination page={data.page} pageSize={data.pageSize} total={data.total} onPageChange={(p) => setF((prev) => ({ ...prev, page: p }))} />
        </>
      )}

      {target && (
        <UploadDocsModal
          key={`${target.row.storeId}-${target.kind}`}
          storeId={target.row.storeId}
          storeName={target.row.name}
          month={month}
          monthLabel={monthLabel(month)}
          kind={target.kind}
          replacing={Boolean(target.row[target.kind])}
          onClose={() => setTarget(null)}
        />
      )}

      {bulk && <BulkUploadModal month={month} months={data?.months ?? [month]} onClose={() => setBulk(false)} />}

      <Modal
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title={`Remove ${removing ? DOC_LABEL[removing.kind] : "document"}?`}
        description={removing ? `${removing.name} · ${monthLabel(month)}` : undefined}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRemoving(null)}>Cancel</Button>
            <Button variant="danger" isLoading={remove.isPending} onClick={() => removing && remove.mutate(removing.doc.id, { onSuccess: () => setRemoving(null) })}>
              Remove
            </Button>
          </>
        }
      >
        <p className="text-sm text-gray-600">It will be taken off this list. The file itself is kept safely and never deleted, and uploading again for this store and month brings it back.</p>
      </Modal>

    </div>
  );
}
