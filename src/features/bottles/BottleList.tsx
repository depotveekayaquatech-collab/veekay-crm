import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { SearchBox } from "@/features/orders/ui";
import {
  PAGE_SIZE, downloadFile, labelPath, useBottleDetail, useBottles, useDeleteCodes, useReplace, useRetire, useScanStores, useSummary, when,
  type Bottle, type BottleState,
} from "@/features/bottles/api";
import { usePermission } from "@/hooks/usePermission";
import { useDebounced } from "@/hooks/useDebounced";

export function StatusBadge({ b }: { b: Bottle }) {
  if (b.overdue) return <Badge tone="danger">Overdue {b.daysAtStore}d</Badge>;
  switch (b.status) {
    case "AT_STORE": return <Badge tone="info">At store{b.daysAtStore != null ? ` · ${b.daysAtStore}d` : ""}</Badge>;
    case "RETURNED": return <Badge tone="success">Returned</Badge>;
    case "RETIRED": return <Badge tone="neutral">Retired</Badge>;
    case "DELETED": return <Badge tone="neutral">Deleted</Badge>;
    default: return <Badge tone="neutral">Not used yet</Badge>;
  }
}

function Tile({ label, value, tone, active, onClick, hint }: { label: string; value: number | undefined; tone?: "danger"; active: boolean; onClick: () => void; hint?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex flex-col items-start justify-start rounded-xl border px-4 py-3 text-left shadow-card transition-colors ${active ? "border-brand-500 bg-surface ring-1 ring-brand-500" : "border-surface-border bg-surface hover:border-gray-300"}`}
    >
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${tone === "danger" && value ? "text-status-danger" : "text-heading"}`}>{value?.toLocaleString("en-IN") ?? "—"}</p>
      <p className="mt-0.5 min-h-[1rem] text-[11px] leading-4 text-gray-500">{hint}</p>
    </button>
  );
}

export function BottleList({ canManage }: { canManage: boolean }) {
  const [state, setState] = useState<BottleState | "">("OVERDUE");
  const [q, setQ] = useState("");
  const [storeId, setStoreId] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const search = useDebounced(q);
  const { data: sum } = useSummary();
  const { data: stores } = useScanStores();
  const { data, isLoading, isError, refetch } = useBottles({ state, q: search, storeId }, page);

  const pick = (s: BottleState | "") => { setState(s); setPage(1); };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Tile label="Overdue" tone="danger" value={sum?.overdue} hint={sum ? `IN, no OUT for ${sum.lostAfterDays}+ days` : "Scanned IN, never OUT"} active={state === "OVERDUE"} onClick={() => pick("OVERDUE")} />
        <Tile label="At stores" hint="Scanned IN, not out yet" value={sum?.atStore} active={state === "AT_STORE"} onClick={() => pick("AT_STORE")} />
        <Tile label="Returned" hint="Scanned OUT" value={sum?.returned} active={state === "RETURNED"} onClick={() => pick("RETURNED")} />
        <Tile label="Not used yet" value={sum?.unused} hint="Printed, never scanned" active={state === "UNUSED"} onClick={() => pick("UNUSED")} />
        <Tile label="Retired" hint="Replaced or written off" value={sum?.retired} active={state === "RETIRED"} onClick={() => pick("RETIRED")} />
        <Tile label="All" hint="Every active code" value={sum?.totalActive} active={state === ""} onClick={() => pick("")} />
        <Tile label="Deleted" hint="History kept" value={sum?.deleted} active={state === "DELETED"} onClick={() => pick("DELETED")} />
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <SearchBox className="min-w-[200px] flex-1" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Search a code, e.g. VK-7F3K" />
        <div className="w-60">
          <Select label="Store" value={storeId} searchable onChange={(e) => { setStoreId(e.target.value); setPage(1); }} options={[{ value: "", label: "All stores" }, ...(stores ?? []).map((s) => ({ value: s.id, label: `${s.name} (${s.code})` }))]} />
        </div>
      </div>

      {isError ? (
        <ErrorState message="Could not load bottles." onRetry={() => refetch()} />
      ) : isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <Table>
            <thead>
              <tr><Th>Code</Th><Th>Status</Th><Th>Store</Th><Th>Last IN</Th><Th>Last OUT</Th></tr>
            </thead>
            <tbody>
              {data?.items.length ? data.items.map((b) => (
                <tr key={b.id} className="cursor-pointer hover:bg-surface-subtle" onClick={() => setOpen(b.serial)}>
                  <Td className="whitespace-nowrap font-mono font-semibold text-gray-900">{b.serial}</Td>
                  <Td><StatusBadge b={b} /></Td>
                  <Td>{b.storeName ?? "—"}</Td>
                  <Td className="whitespace-nowrap">{when(b.lastInAt)}</Td>
                  <Td className="whitespace-nowrap">{when(b.lastOutAt)}</Td>
                </tr>
              )) : <TableEmpty colSpan={5}>{state === "OVERDUE" ? "No overdue bottles — everything scanned IN has come back." : "No bottles match."}</TableEmpty>}
            </tbody>
          </Table>
          {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />}
        </>
      )}
      {open && <BottleModal serial={open} canManage={canManage} onClose={() => setOpen(null)} onOpen={setOpen} />}
    </div>
  );
}

/** One bottle: where it is, its full IN/OUT history, and (for managers) replace-QR / retire. */
export function BottleModal({ serial, canManage, onClose, onOpen }: { serial: string; canManage: boolean; onClose: () => void; onOpen: (s: string) => void }) {
  const { data, isLoading } = useBottleDetail(serial);
  const replace = useReplace();
  const retire = useRetire();
  const del = useDeleteCodes();
  const canDelete = usePermission("bottles.delete");
  const [reason, setReason] = useState("");
  const b = data?.bottle;

  return (
    <Modal open onClose={onClose} title={serial} size="lg" description="Scan history, newest first">
      {isLoading || !b ? <Skeleton className="h-40 w-full" /> : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge b={b} />
            {b.storeName && <span className="text-sm text-gray-700">{b.status === "AT_STORE" ? "At" : "Last at"} <b>{b.storeName}</b></span>}
          </div>
          {b.replacedBySerial && <p className="text-sm text-gray-600">Replaced by <button className="font-mono font-semibold text-brand-700 underline" onClick={() => onOpen(b.replacedBySerial!)}>{b.replacedBySerial}</button>{b.retireReason ? ` — ${b.retireReason}` : ""}</p>}
          {b.replacesSerial && <p className="text-sm text-gray-600">Replaces <button className="font-mono font-semibold text-brand-700 underline" onClick={() => onOpen(b.replacesSerial!)}>{b.replacesSerial}</button> (damaged QR)</p>}
          {b.status === "RETIRED" && !b.replacedBySerial && <p className="text-sm text-gray-600">Retired: {b.retireReason}</p>}
          {b.status === "DELETED" && <p className="text-sm text-gray-600">Deleted {when(b.retiredAt)}: {b.retireReason}. This code can never be scanned again; its history stays below.</p>}

          <Table>
            <thead><tr><Th>When</Th><Th>Scan</Th><Th>Store</Th><Th>By</Th></tr></thead>
            <tbody>
              {data.scans.length ? data.scans.map((s) => (
                <tr key={s.id}>
                  <Td className="whitespace-nowrap">{when(s.scannedAt)}</Td>
                  <Td><Badge tone={s.direction === "IN" ? "info" : "success"}>{s.direction}</Badge>{s.warning && <p className="mt-1 text-xs text-status-warning">{s.warning}</p>}</Td>
                  <Td>{s.storeName ?? "—"}</Td>
                  <Td>{s.scannedByName ?? "—"}{s.source === "api" ? " (API)" : ""}</Td>
                </tr>
              )) : <TableEmpty colSpan={4}>Never scanned.</TableEmpty>}
            </tbody>
          </Table>

          {canDelete && b.status !== "DELETED" && (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-status-danger p-3">
              <p className="text-sm text-gray-700">Delete this code so it can never be scanned again. The record and its {data.scans.length} scan(s) stay on file.</p>
              <Button
                variant="danger"
                isLoading={del.isPending}
                onClick={() => window.confirm(`Delete ${b.serial}?\n\nIt can never be scanned again. Its history is kept.`) && del.mutate({ serials: [b.serial], reason }, { onSuccess: onClose })}
              >
                Delete code
              </Button>
            </div>
          )}
          {canManage && b.status !== "RETIRED" && b.status !== "DELETED" && (
            <div className="flex flex-col gap-3 rounded-xl border border-surface-border p-3">
              <Input label="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. QR torn, bottle destroyed" />
              <div className="flex flex-wrap gap-2">
                <Button
                  isLoading={replace.isPending}
                  onClick={() => replace.mutate({ serial: b.serial, reason }, {
                    onSuccess: (r) => {
                      downloadFile(labelPath(r.new.serial), `${r.new.serial}.pdf`, true).catch(() => undefined);
                      onOpen(r.new.serial);
                    },
                  })}
                >
                  QR damaged — issue new code
                </Button>
                <Button variant="danger" isLoading={retire.isPending} onClick={() => window.confirm(`Retire ${b.serial}? It can no longer be scanned.`) && retire.mutate({ serial: b.serial, reason })}>
                  Retire bottle
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
