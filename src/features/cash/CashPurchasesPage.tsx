import { useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Table, Td, TableEmpty, Th } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { SearchBox, SegmentedControl } from "@/features/orders/ui";
import { AddPurchaseModal } from "@/features/cash/AddPurchaseModal";
import {
  PAGE_SIZE,
  downloadCashSheet,
  inr,
  openProof,
  useCashOptions,
  useCashPurchases,
  type CashFilters,
} from "@/features/cash/api";
import { usePermission } from "@/hooks/usePermission";

const EMPTY: CashFilters = { kind: "", start: "", end: "", category: "", q: "" };

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface px-4 py-3 shadow-card">
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums text-heading">{value}</p>
    </div>
  );
}

export function CashPurchasesPage() {
  const canAdd = usePermission("cash.add");
  const canViewAll = usePermission("cash.view");
  const { data: options } = useCashOptions();
  const [filters, setFilters] = useState<CashFilters>(EMPTY);
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const { data, isLoading, isError, refetch, isFetching } = useCashPurchases(filters, page);

  function set(patch: Partial<CashFilters>) {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  }

  // The reason filter follows the Office / Store switch (both lists when neither is picked).
  const reasonOptions = useMemo(() => {
    if (!options) return [];
    const list =
      filters.kind === "OFFICE"
        ? options.officeReasons
        : filters.kind === "STORE"
          ? options.storeReasons
          : [...options.officeReasons, ...options.storeReasons];
    const seen = new Set<string>();
    return list.filter((r) => !seen.has(r.code) && seen.add(r.code)).map((r) => ({ value: r.code, label: r.label }));
  }, [options, filters.kind]);

  async function download() {
    setDownloading(true);
    try {
      await downloadCashSheet(filters);
    } catch {
      /* the API layer already showed the reason */
    } finally {
      setDownloading(false);
    }
  }

  const filtered = Boolean(filters.kind || filters.start || filters.end || filters.category || filters.q);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Cash purchases"
        subtitle={canViewAll ? "Everything paid in cash for the office and the stores." : "Cash purchases you have recorded."}
        action={
          <div className="flex flex-wrap gap-2">
            {canViewAll && (
              <Button variant="secondary" onClick={download} isLoading={downloading}>
                Download sheet
              </Button>
            )}
            {canAdd && (
              <Button onClick={() => setAdding(true)} disabled={!options}>
                Add purchase
              </Button>
            )}
          </div>
        }
      />

      <div className="flex flex-wrap items-end gap-3">
        <SegmentedControl
          label="Type"
          value={filters.kind}
          onChange={(v) => set({ kind: v, category: "" })}
          options={[
            { value: "", label: "All" },
            { value: "OFFICE", label: "Office" },
            { value: "STORE", label: "Stores" },
          ]}
        />
        <div className="w-48">
          <Select label={filters.kind === "STORE" ? "Reason" : "Purchase"} value={filters.category} onChange={(e) => set({ category: e.target.value })} options={[{ value: "", label: "All" }, ...reasonOptions]} />
        </div>
        <div className="w-40">
          <Input label="From" type="date" value={filters.start} max={filters.end || undefined} onChange={(e) => set({ start: e.target.value })} />
        </div>
        <div className="w-40">
          <Input label="To" type="date" value={filters.end} min={filters.start || undefined} onChange={(e) => set({ end: e.target.value })} />
        </div>
        <SearchBox className="min-w-[200px] flex-1" value={filters.q} onChange={(v) => set({ q: v })} placeholder="Search notes or description" />
        {filtered && (
          <Button variant="ghost" onClick={() => set(EMPTY)}>
            Clear
          </Button>
        )}
      </div>

      {isError ? (
        <ErrorState message="Could not load cash purchases." onRetry={() => refetch()} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="Total" value={data ? inr(data.amountTotal) : "—"} />
            <Stat label="Office" value={data ? inr(data.officeTotal) : "—"} />
            <Stat label="Stores" value={data ? inr(data.storeTotal) : "—"} />
          </div>

          {isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <div className={isFetching ? "opacity-70 transition-opacity" : "transition-opacity"}>
              <Table>
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th>For</Th>
                    <Th>Purchase</Th>
                    <Th>Proof</Th>
                    {canViewAll && <Th>Added by</Th>}
                    <Th className="text-right">Amount</Th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.length ? (
                    data.items.map((p) => (
                      <tr key={p.id}>
                        <Td className="whitespace-nowrap tabular-nums">{p.purchaseDate}</Td>
                        <Td>
                          {p.kind === "OFFICE" ? (
                            <Badge tone="info">Office</Badge>
                          ) : (
                            <span className="flex flex-col">
                              <span className="font-medium text-gray-900">{p.storeName}</span>
                              <span className="text-xs text-gray-500">{p.storeCode}</span>
                            </span>
                          )}
                        </Td>
                        <Td>
                          <span className="font-medium text-gray-900">{p.kind === "STORE" ? "Water bottles" : p.categoryLabel}</span>
                          {p.kind === "STORE" && <p className="text-xs text-gray-600">Reason: {p.categoryLabel}</p>}
                          {(p.otherReason || p.notes) && <p className="mt-0.5 max-w-xs text-xs text-gray-500">{[p.otherReason, p.notes].filter(Boolean).join(" — ")}</p>}
                        </Td>
                        <Td>
                          {p.hasProof ? (
                            <Button size="sm" variant="secondary" onClick={() => openProof(p.id).catch(() => undefined)}>
                              View
                            </Button>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </Td>
                        {canViewAll && <Td>{p.addedBy ?? "—"}</Td>}
                        <Td className="whitespace-nowrap text-right font-semibold tabular-nums text-gray-900">{inr(p.amount)}</Td>
                      </tr>
                    ))
                  ) : (
                    <TableEmpty colSpan={canViewAll ? 6 : 5}>{filtered ? "No purchases match these filters." : "No cash purchases recorded yet."}</TableEmpty>
                  )}
                </tbody>
              </Table>
            </div>
          )}
          {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />}
        </>
      )}

      {adding && options && <AddPurchaseModal options={options} onClose={() => setAdding(false)} />}
    </div>
  );
}
