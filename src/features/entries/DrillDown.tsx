import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { pushToast } from "@/lib/toast";
import { useEmployeeStores, useVerifyStore, type Filters, type PlatformOption, type StoreOfEmployee } from "@/features/entries/api";
import { fmtDay } from "@/features/entries/format";

/** The Partner (Blinkit / Zepto) dropdown. It disappears when the caller can only look into one partner (a Blinkit Reviewer), who then just sees their employees. */
export function PartnerSelect({ platforms, value, onChange }: { platforms: PlatformOption[]; value: string; onChange: (slug: string) => void }) {
  if (platforms.length < 2) return null;
  return (
    <Select label="Partner" value={value} onChange={(e) => onChange(e.target.value)}
      options={[{ value: "", label: "All partners" }, ...platforms.map((p) => ({ value: p.slug, label: p.name }))]} />
  );
}

/** "All entries › Priti › SS Kolkata Bally": where you are in the drill-down, and a way back up each step. */
export function Crumbs({ person, store, onAll, onPerson }: { person?: string; store?: string; onAll: () => void; onPerson?: () => void }) {
  if (!person && !store) return null;
  const link = "font-semibold text-brand-600 hover:underline";
  return (
    <nav aria-label="Where you are" className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
      <button type="button" className={link} onClick={onAll}>All entries</button>
      {person && <><span aria-hidden="true">›</span>{store && onPerson ? <button type="button" className={link} onClick={onPerson}>{person}</button> : <b className="text-gray-900">{person}</b>}</>}
      {person && store && <span className="text-xs text-gray-500">(stores)</span>}
      {store && <><span aria-hidden="true">›</span><b className="text-gray-900">{store}</b></>}
    </nav>
  );
}

/**
 * Step two of the drill-down: after an employee is chosen, THEIR stores come first, each with how many of the employee's entries are pending, verified and
 * reviewed. Opening a store shows that store's entries, date by date.
 */
export function EmployeeStoresTable({ creatorId, filters, onOpenStore }: { creatorId: string; filters: Filters; onOpenStore: (store: { id: string; name: string }) => void }) {
  const q = useEmployeeStores(creatorId, filters);
  const verifyStore = useVerifyStore();
  const [busyId, setBusyId] = useState<string | null>(null);
  if (q.isLoading) return <Skeleton className="h-48" />;
  if (q.isError) return <ErrorState message={q.error instanceof Error ? q.error.message : "Couldn't load this employee's stores."} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d) return null;
  const reviewing = d.verify_to === "reviewed_l3";
  /** One click for a whole store of this employee: a Team Lead verifies what is waiting, a Reviewer marks everything not yet reviewed as reviewed. */
  function verifyWhole(r: StoreOfEmployee, todo: number) {
    if (!window.confirm(`${reviewing ? "Mark reviewed" : "Verify"} ${todo} entr${todo === 1 ? "y" : "ies"} of ${d!.employee.name} in ${r.store.name}?`)) return;
    setBusyId(r.store.id);
    verifyStore.mutate({ storeId: r.store.id, creatorId, dateFrom: filters.date_from as string | undefined, dateTo: filters.date_to as string | undefined }, {
      onSettled: () => setBusyId(null),
      onError: (e) => pushToast(e instanceof Error ? e.message : "That didn't work.", "error"),
    });
  }
  return (
    <>
      <p className="text-sm text-gray-500">
        <b className="text-gray-900">{d.employee.name}</b> ({d.employee.code}) has entered {d.total.toLocaleString()} store{d.total === 1 ? "" : "s"}. Open a store to see its entries.
      </p>
      <Table>
        <thead>
          <tr>
            <Th>Store</Th><Th className="text-right">Entries</Th><Th className="text-right">Pending Team Lead</Th><Th className="text-right">Verified</Th>
            <Th className="text-right">Reviewed</Th><Th className="text-right">Bottles</Th><Th>Last entry</Th><Th className="text-right">Entries</Th>
          </tr>
        </thead>
        <tbody>
          {d.items.length === 0 && <TableEmpty colSpan={8}>No stores match these filters for this employee.</TableEmpty>}
          {d.items.map((r) => (
            <tr key={r.store.id} className="cursor-pointer hover:bg-surface-subtle/70" onClick={() => onOpenStore({ id: r.store.id, name: r.store.name })}>
              <Td>
                <span className="font-semibold text-gray-900">{r.store.name}</span>
                <span className="block text-xs text-gray-500">{r.store.outlet_id}{r.store.crm_code ? ` · ${r.store.crm_code}` : ""}{r.store.entity ? ` · ${r.store.entity}` : ""}{r.store.status !== "LIVE" ? ` · ${r.store.status}` : ""}</span>
              </Td>
              <Td className="text-right font-bold tabular-nums">{r.entries}</Td>
              <Td className="text-right">
                {r.pending_l2 ? <Badge tone="warning">{r.pending_l2}</Badge> : <span className="text-gray-400">0</span>}
                {r.requested ? <span className="ml-1 text-[11px] font-semibold text-amber-700">{r.requested} requested</span> : null}
              </Td>
              <Td className="text-right">{r.verified_l2 ? <Badge tone="info">{r.verified_l2}</Badge> : <span className="text-gray-400">0</span>}</Td>
              <Td className="text-right">{r.reviewed_l3 ? <Badge tone="success">{r.reviewed_l3}</Badge> : <span className="text-gray-400">0</span>}</Td>
              <Td className="text-right tabular-nums">{r.bottles.toLocaleString()}</Td>
              <Td className="whitespace-nowrap text-xs">{fmtDay(r.last_entry)}</Td>
              <Td className="text-right">
                <div className="flex flex-wrap items-center justify-end gap-1.5">
                  {d.verify_to && (reviewing ? r.pending_l2 + r.verified_l2 : r.pending_l2) > 0 && (
                    <Button size="sm" isLoading={busyId === r.store.id} onClick={(e) => { e.stopPropagation(); verifyWhole(r, reviewing ? r.pending_l2 + r.verified_l2 : r.pending_l2); }}>
                      {reviewing ? "Mark store reviewed" : "Verify store"}
                    </Button>
                  )}
                  <Button size="sm" variant="secondary" onClick={(e) => { e.stopPropagation(); onOpenStore({ id: r.store.id, name: r.store.name }); }}>Open</Button>
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </>
  );
}
