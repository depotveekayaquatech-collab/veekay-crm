import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Table, Td, TableEmpty, Th } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { SegmentedControl } from "@/features/orders/ui";
import {
  SYNC_PAGE_SIZE,
  ceilQty,
  downloadPurchaseSheet,
  useStoreChoices,
  useSyncActions,
  useSyncRecords,
  when,
  type SyncApplyResult,
  type SyncPreview,
  type SyncRecord,
  type SyncStatus,
  type SyncSummary,
} from "@/features/datasync/cashApi";
import { daysAgo } from "@/lib/dates";

const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
const TONE = { PENDING: "info", CHANGED: "warning", APPLIED: "success", SKIPPED: "neutral" } as const;

function Row({
  r, stores, selected, onToggle, actions,
}: {
  r: SyncRecord;
  stores: { value: string; label: string }[];
  selected: boolean;
  onToggle: () => void;
  actions: ReturnType<typeof useSyncActions>;
}) {
  const today = daysAgo(0);
  const locked = r.status === "APPLIED";
  const [amount, setAmount] = useState(r.amount);
  const [price, setPrice] = useState(r.pricePerItem ?? "");
  const [qty, setQty] = useState<string>(r.finalQty != null ? String(r.finalQty) : "");
  const [prev, setPrev] = useState(r);
  // Keep the cells in step with what the server calculated (after an edit or a refetch).
  if (prev !== r) {
    setPrev(r);
    setAmount(r.amount);
    setPrice(r.pricePerItem ?? "");
    setQty(r.finalQty != null ? String(r.finalQty) : "");
  }
  const save = (patch: Parameters<typeof actions.edit.mutate>[0] extends infer P ? Omit<P, "id"> : never) => actions.edit.mutate({ id: r.id, ...patch });
  const liveAuto = ceilQty(amount, price);

  return (
    <>
      <tr className={r.status === "CHANGED" ? "bg-status-warning-soft/40" : undefined}>
        <Td>{r.status === "PENDING" && <input type="checkbox" className="h-4 w-4" checked={selected} onChange={onToggle} aria-label={`Select ${r.purchaseCode}`} />}</Td>
        <Td className="whitespace-nowrap">
          <span className="font-mono text-xs text-gray-600">{r.purchaseCode}</span>
          <div><Badge tone={TONE[r.status]}>{r.status === "CHANGED" ? "Changed" : r.status.charAt(0) + r.status.slice(1).toLowerCase()}</Badge></div>
        </Td>
        <Td className="min-w-56 [&_label]:sr-only">
          {locked ? (
            <span>{r.outletName} <span className="text-xs text-gray-500">{r.outletCode}</span></span>
          ) : (
            <Select label="Store" searchable value={r.storeId ?? ""} options={stores} placeholder="Pick a store" onChange={(e) => save({ storeId: e.target.value })} />
          )}
        </Td>
        <Td className="[&_label]:sr-only">
          {locked ? day(r.purchaseDate) : <Input label="Date" type="date" value={r.purchaseDate} max={today} onChange={(e) => e.target.value && save({ purchaseDate: e.target.value })} />}
        </Td>
        <Td className="w-28 [&_label]:sr-only">
          {locked ? `₹${r.amount}` : <Input label="Amount" type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} onBlur={() => amount !== r.amount && Number(amount) > 0 && save({ amount })} />}
        </Td>
        <Td className="w-28 [&_label]:sr-only">
          {locked ? (r.pricePerItem ? `₹${r.pricePerItem}` : "—") : <Input label="Price" type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} onBlur={() => price !== (r.pricePerItem ?? "") && Number(price) > 0 && save({ pricePerItem: price })} />}
        </Td>
        <Td className="text-center tabular-nums">{locked ? r.autoQty ?? "—" : (price === (r.pricePerItem ?? "") && amount === r.amount ? r.autoQty : liveAuto) ?? "—"}</Td>
        <Td className="w-24 [&_label]:sr-only">
          {locked ? <b>{r.appliedQty}</b> : <Input label="Final qty" type="number" min="1" step="1" value={qty} onChange={(e) => setQty(e.target.value)} onBlur={() => qty !== (r.finalQty != null ? String(r.finalQty) : "") && /^\d+$/.test(qty) && save({ finalQty: Number(qty) })} />}
        </Td>
        <Td className="whitespace-nowrap text-right">
          {r.status === "PENDING" && <Button size="sm" variant="ghost" onClick={() => actions.resolve.mutate({ id: r.id, action: "skip" })}>Skip</Button>}
          {r.status === "SKIPPED" && <Button size="sm" variant="ghost" onClick={() => actions.resolve.mutate({ id: r.id, action: "unskip" })}>Restore</Button>}
        </Td>
      </tr>
      {r.status === "CHANGED" && r.previousSource && r.currentSource && (
        <tr className="bg-status-warning-soft/40">
          <Td colSpan={9} className="text-sm">
            <p className="font-semibold text-status-warning">Review required — the source purchase changed after the last sync.</p>
            <p className="mt-1 text-gray-700">
              Before: {r.previousSource.storeName ?? "—"} · {day(r.previousSource.purchaseDate)} · ₹{r.previousSource.amount} &nbsp;→&nbsp; Now: {r.currentSource.storeName ?? "—"} · {day(r.currentSource.purchaseDate)} · ₹{r.currentSource.amount}
              {r.everApplied && <span className="ml-2 text-gray-500">(+{r.appliedQty} was already added to the order sheet)</span>}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {r.everApplied ? (
                <>
                  <Button size="sm" variant="secondary" onClick={() => actions.resolve.mutate({ id: r.id, action: "acknowledge" })}>Keep what was applied</Button>
                  <Button size="sm" variant="secondary" onClick={() => actions.resolve.mutate({ id: r.id, action: "reopen" })}>Reopen as a new adjustment</Button>
                </>
              ) : (
                <>
                  <Button size="sm" variant="secondary" onClick={() => actions.resolve.mutate({ id: r.id, action: "accept_source" })}>Use the new values</Button>
                  <Button size="sm" variant="secondary" onClick={() => actions.resolve.mutate({ id: r.id, action: "keep_mine" })}>Keep my edits</Button>
                  <Button size="sm" variant="ghost" onClick={() => actions.resolve.mutate({ id: r.id, action: "skip" })}>Skip</Button>
                </>
              )}
            </div>
          </Td>
        </tr>
      )}
    </>
  );
}

export function SyncTab() {
  const [status, setStatus] = useState<SyncStatus | "">("PENDING");
  const [page, setPage] = useState(1);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [defaultPrice, setDefaultPrice] = useState("");
  const [replacePrices, setReplacePrices] = useState(false);
  const [summary, setSummary] = useState<SyncSummary | null>(null);
  const [preview, setPreview] = useState<SyncPreview | null>(null);
  const [result, setResult] = useState<SyncApplyResult | null>(null);
  const [downloading, setDownloading] = useState(false);
  const actions = useSyncActions();
  const { data, isLoading } = useSyncRecords(status, page);
  const { data: storeList = [] } = useStoreChoices("");
  const stores = storeList.map((s) => ({ value: s.id, label: `${s.name} (${s.code})` }));

  const pending = (data?.items ?? []).filter((r) => r.status === "PENDING");
  const counts = data?.counts;

  async function doSync() {
    setResult(null);
    try {
      setSummary(await actions.sync.mutateAsync());
    } catch {
      /* shown by the API layer */
    }
  }

  async function applyStandardRate() {
    if (!(Number(defaultPrice) > 0)) return;
    const n = counts?.PENDING ?? 0;
    const msg = replacePrices
      ? `Set ₹${defaultPrice} on all ${n} purchases waiting for review, replacing any price already entered?`
      : `Set ₹${defaultPrice} on every purchase waiting for review that has no price yet?`;
    if (!window.confirm(msg)) return;
    try {
      await actions.standardRate.mutateAsync({ price: defaultPrice, overwrite: replacePrices });
    } catch {
      /* shown by the API layer */
    }
  }

  async function doPreview() {
    try {
      setPreview(await actions.preview.mutateAsync([...picked]));
    } catch {
      /* shown by the API layer */
    }
  }

  async function doApply() {
    try {
      const r = await actions.apply.mutateAsync([...picked]);
      setResult(r);
      setPreview(null);
      setPicked(new Set());
    } catch {
      /* shown by the API layer */
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-4 rounded-2xl border border-surface-border bg-surface p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-heading">Cash purchase sheet</h3>
            <p className="mt-1 text-sm text-gray-500">Sync only brings the latest store purchases here for review. Nothing reaches the order sheet until you confirm.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" isLoading={downloading} onClick={async () => { setDownloading(true); try { await downloadPurchaseSheet(); } catch { /* shown */ } finally { setDownloading(false); } }}>
              Download Cash Purchase Sheet
            </Button>
            <Button onClick={doSync} isLoading={actions.sync.isPending}>
              Sync Cash Purchase
            </Button>
          </div>
        </div>
        {actions.sync.isPending && (
          <p role="status" className="rounded-xl bg-surface-subtle px-4 py-3 text-sm text-gray-700">
            Syncing store purchases… fetching the latest data, checking stores, dates and amounts.
          </p>
        )}
        {(summary ?? data?.lastSync) && !actions.sync.isPending && (() => {
          const s = (summary ?? data?.lastSync) as SyncSummary;
          return (
            <div role="status" className="rounded-xl bg-surface-subtle px-4 py-3 text-sm">
              <p className="font-semibold text-heading">
                {summary ? "Sync completed." : "Last sync"} <span className="font-mono text-xs text-gray-500">{s.syncCode}</span> · {when(s.syncedAt)}
              </p>
              <p className="mt-1 text-gray-700">
                Records synced <b>{s.recordsFound}</b> · New <b>{s.newRecords}</b> · Changed <b>{s.changedRecords}</b> · Already processed <b>{s.alreadyProcessed}</b> · Waiting for review <b>{s.pendingReview}</b>
              </p>
            </div>
          );
        })()}
      </section>

      <div className="flex flex-wrap items-end gap-3">
        <SegmentedControl
          label="Show"
          value={status}
          onChange={(v) => { setStatus(v); setPage(1); setPicked(new Set()); }}
          options={[
            { value: "PENDING", label: `To review${counts ? ` (${counts.PENDING})` : ""}` },
            { value: "CHANGED", label: `Changed${counts ? ` (${counts.CHANGED})` : ""}` },
            { value: "APPLIED", label: `Applied${counts ? ` (${counts.APPLIED})` : ""}` },
            { value: "SKIPPED", label: `Skipped${counts ? ` (${counts.SKIPPED})` : ""}` },
            { value: "", label: "All" },
          ]}
        />
        {status === "PENDING" && (
          <div className="ml-auto flex flex-wrap items-end gap-2">
            <div className="w-40">
              <Input label="Standard rate (₹)" type="number" min="0" step="0.01" value={defaultPrice} onChange={(e) => setDefaultPrice(e.target.value)} />
            </div>
            <label className="flex h-10 cursor-pointer items-center gap-2 text-sm text-gray-600">
              <input type="checkbox" className="h-4 w-4" checked={replacePrices} onChange={(e) => setReplacePrices(e.target.checked)} />
              Replace prices already set
            </label>
            <Button variant="secondary" onClick={applyStandardRate} isLoading={actions.standardRate.isPending} disabled={!(Number(defaultPrice) > 0) || !(counts?.PENDING ?? 0)}>
              Apply to all ({counts?.PENDING ?? 0})
            </Button>
          </div>
        )}
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th className="w-10">
                {status === "PENDING" && pending.length > 0 && (
                  <input type="checkbox" className="h-4 w-4" aria-label="Select all" checked={pending.every((r) => picked.has(r.id))} onChange={(e) => setPicked(e.target.checked ? new Set(pending.map((r) => r.id)) : new Set())} />
                )}
              </Th>
              <Th>Purchase</Th>
              <Th>Store</Th>
              <Th>Date</Th>
              <Th>Cash purchase</Th>
              <Th>Price</Th>
              <Th className="text-center">Calculated qty</Th>
              <Th>Final qty</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {data?.items.length ? (
              data.items.map((r) => (
                <Row key={r.id} r={r} stores={stores} actions={actions} selected={picked.has(r.id)}
                  onToggle={() => setPicked((p) => { const n = new Set(p); if (n.has(r.id)) n.delete(r.id); else n.add(r.id); return n; })} />
              ))
            ) : (
              <TableEmpty colSpan={9}>{data?.lastSync ? "Nothing here. Sync again to look for new purchases." : "No synced purchases yet. Click Sync Cash Purchase."}</TableEmpty>
            )}
          </tbody>
        </Table>
      )}
      {data && <Pagination page={page} pageSize={SYNC_PAGE_SIZE} total={data.total} onPageChange={setPage} />}

      {result && (
        <section className="flex flex-col gap-2 rounded-2xl border border-surface-border bg-surface p-5 text-sm shadow-card">
          <p className="font-bold text-heading">Applied {result.appliedRecords} purchase{result.appliedRecords === 1 ? "" : "s"} to {result.appliedRows.length} store/day</p>
          <ul className="text-gray-600">
            {result.appliedRows.map((r) => (
              <li key={`${r.storeId}-${r.purchaseDate}`}>{r.outletName} · {day(r.purchaseDate)}: {r.previous} → <b>{r.newTotal}</b></li>
            ))}
          </ul>
          {result.failed.length > 0 && (
            <ul className="list-disc rounded-lg bg-status-danger-soft px-4 py-2 pl-8 text-status-danger">
              {result.failed.map((f, i) => <li key={i}>Not updated: {f.outletName} · {day(f.purchaseDate)} — {f.error}</li>)}
            </ul>
          )}
        </section>
      )}

      {status === "PENDING" && (
        <div className="sticky bottom-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-surface-border bg-surface p-4 shadow-card">
          <p className="text-sm text-gray-600">{picked.size} selected</p>
          <Button onClick={doPreview} disabled={!picked.size} isLoading={actions.preview.isPending}>
            Preview order changes
          </Button>
        </div>
      )}

      <Modal
        open={Boolean(preview)}
        onClose={() => setPreview(null)}
        title="Final cash purchase preview"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setPreview(null)}>Cancel</Button>
            <Button onClick={doApply} isLoading={actions.apply.isPending} disabled={!preview?.canApply}>Apply changes</Button>
          </>
        }
      >
        {preview && (
          <div className="flex flex-col gap-4 text-sm">
            <p className="text-gray-600">
              Stores <b>{preview.totalStores}</b> · Purchases <b>{preview.totalRecords}</b> · Total quantity added <b>{preview.totalQty}</b>
            </p>
            <ul className="divide-y divide-surface-border rounded-xl border border-surface-border">
              {preview.rows.map((r) => (
                <li key={`${r.storeId}-${r.purchaseDate}`} className="px-4 py-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span><span className="font-medium text-gray-900">{r.outletName}</span> <span className="text-xs text-gray-500">{r.outletCode} · {day(r.purchaseDate)}</span></span>
                    <span className="tabular-nums">{r.employeeEntry !== null ? `Employee entry ${r.employeeEntry} · ` : ""}+{r.added} → <b>{r.newTotal}</b></span>
                  </div>
                  {r.purchases.length > 1 && <p className="mt-0.5 text-xs text-gray-500">{r.purchases.map((p) => `${p.purchaseCode} +${p.finalQty ?? "?"}`).join(" · ")}</p>}
                  {r.error && <p className="mt-0.5 text-xs text-status-danger">{r.error}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Modal>
    </div>
  );
}
