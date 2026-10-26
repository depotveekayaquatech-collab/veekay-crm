import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useAttempts, useEntrySearch, usePlatforms, useSecurityEvents } from "@/features/entries/api";
import { Crumbs, EmployeeStoresTable, PartnerSelect } from "@/features/entries/DrillDown";
import { EntryDrawer } from "@/features/entries/EntryDrawer";
import { EntryPicker, StatusChips } from "@/features/entries/EntryFilters";
import { EntryResultsTable } from "@/features/entries/EntryResultsTable";
import { StoreReviewPanel } from "@/features/entries/StoreReviewPanel";
import { STATUS_FILTER_OPTIONS, fmtDay, fmtMoment } from "@/features/entries/format";
import { useEntryFilters } from "@/features/entries/useEntryFilters";

type Tab = "entries" | "removed" | "attempts" | "security";

const TRI = [{ value: "", label: "Any" }, { value: "true", label: "Yes" }, { value: "false", label: "No" }];

/**
 * Entry Review (Level 3 Reviewer and Level 4 Administrator): the work queue starts on the entries the Team Lead has verified ("ready to review"); find ANY
 * entry in scope by store, employee, team lead, date/time or state, and open it in the verification panel to edit, review it yourself, ask the Team Lead to
 * check it, or read its full history. Every search runs on the server and is paginated; nothing depends on what the browser has loaded.
 */
export function StoreAuditPage() {
  const [tab, setTab] = useState<Tab>("entries");
  const f = useEntryFilters("verified_l2");
  const { draft, applied, page, setPage } = f;
  const [open, setOpen] = useState<string | null>(null);
  const [storeName, setStoreName] = useState("");
  const [personName, setPersonName] = useState("");
  const [more, setMore] = useState(false);
  const [secType, setSecType] = useState("");
  const platforms = usePlatforms();
  const platformId = platforms.data?.find((p) => p.slug === draft.platform)?.id ?? "";

  // Drill-down: Partner -> Employee -> that employee's STORES -> one store's entries. With an employee chosen and no store yet, the stores come first.
  const employeeId = (applied.creator_id as string) ?? "";
  const storeId = (applied.store_id as string) ?? "";
  const showStores = tab === "entries" && Boolean(employeeId) && !storeId && !((applied.store as string) ?? "").trim();
  const search = useEntrySearch(tab === "removed" ? { ...applied, verification: "", deleted: true } : applied, page, 25, !showStores);
  const attempts = useAttempts({ store: applied.store as string, store_id: applied.store_id as string, outcome: applied.attempt_outcome as string, date_from: applied.date_from as string, date_to: applied.date_to as string }, page, tab === "attempts");
  const security = useSecurityEvents(secType, page, tab === "security");

  const set = f.set;
  const apply = f.search;
  const reset = () => { setStoreName(""); setPersonName(""); f.reset(); };
  const changeTab = (t: Tab) => { setTab(t); setPage(1); };
  const input = (k: string, label: string, placeholder?: string) => (
    <Input label={label} value={(draft[k] as string) ?? ""} onChange={(e) => set(k)(e.target.value)} placeholder={placeholder} />
  );

  const tabs: [Tab, string][] = [["entries", "Entries"], ["removed", "Removed entries"], ["attempts", "Attempts (saved, refused, repeated)"], ["security", "Security log"]];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Entry Review" subtitle="Review entries after the Team Lead, or step in yourself. Trace any entry to the person who created it, when, and every change since. Searches run on the server over everything you are allowed to see." />

      <div role="tablist" className="flex flex-wrap gap-1.5">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => changeTab(id)}
            className={`rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors ${tab === id ? "bg-brand-500 text-white shadow-sm" : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === "entries" && <StatusChips active={(draft.verification as string) ?? ""} onPick={f.chooseStatus} />}

      {(tab === "entries" || tab === "removed" || tab === "attempts") && (
        <form className="grid gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => { e.preventDefault(); apply(); }}>
          {tab === "entries" && (
            <>
              <PartnerSelect platforms={platforms.data ?? []} value={(draft.platform as string) ?? ""} onChange={(slug) => { setPersonName(""); setStoreName(""); f.pick("platform", slug); }} />
              <EntryPicker kind="person" label="Employee" placeholder="Choose an employee…" value={(draft.creator_id as string) ?? ""} valueLabel={personName} platformId={platformId}
                onPick={(id, label) => { setPersonName(label ?? ""); setStoreName(""); f.pick("creator_id", id); }} />
              <EntryPicker kind="store" label="Store" placeholder="Search a store…" value={(draft.store_id as string) ?? ""} valueLabel={storeName} onPick={(id, label) => { setStoreName(label ?? ""); f.pick("store_id", id); }} />
              <Select label="Status" value={(draft.verification as string) ?? ""} onChange={(e) => f.chooseStatus(e.target.value)} options={STATUS_FILTER_OPTIONS} />
            </>
          )}
          <Input label="Day from" type="date" value={(draft.date_from as string) ?? ""} onChange={(e) => set("date_from")(e.target.value)} />
          <Input label="Day to" type="date" value={(draft.date_to as string) ?? ""} onChange={(e) => set("date_to")(e.target.value)} />
          {(tab !== "entries" || more) && input("store", "Store name, code or outlet", "e.g. CPC Sonipat")}
          {(tab !== "entries" || more) && tab !== "attempts" && input("outlet_id", "Outlet ID (exact)")}
          {(tab !== "entries" || more) && tab !== "attempts" && input("entry_id", "Entry ID (exact)")}
          {tab !== "entries" && input("store_id", "Store ID (exact)")}
          {tab === "entries" && more && (
            <>
              {input("creator", "Creator name or employee ID (text)")}
              <Select label="Creator role" value={(draft.creator_role as string) ?? ""} onChange={(e) => set("creator_role")(e.target.value)}
                options={[{ value: "", label: "Any" }, { value: "entry_contributor", label: "Data Entry" }, { value: "team_lead", label: "Team Lead" }, { value: "entry_reviewer", label: "Reviewer" }, { value: "administrator", label: "Administrator" }, { value: "developer", label: "Developer" }]} />
              {input("team_lead", "Team Lead name or ID")}
              {input("modifier", "Last changed by")}
            </>
          )}
          {(tab === "removed" || (tab === "entries" && more)) && (
            <>
              <Input label="Created / changed from (IST)" type="datetime-local" value={(draft.created_from as string) ?? ""} onChange={(e) => set("created_from")(e.target.value)} />
              <Input label="Created / changed to (IST)" type="datetime-local" value={(draft.created_to as string) ?? ""} onChange={(e) => set("created_to")(e.target.value)} />
            </>
          )}
          {tab === "entries" && more && (
            <>
              <Select label="Flag" value={(draft.review_status as string) ?? ""} onChange={(e) => set("review_status")(e.target.value)}
                options={[{ value: "", label: "Any" }, { value: "none", label: "No mark" }, { value: "flagged", label: "Flagged" }, { value: "needs_correction", label: "Needs correction" }]} />
              <Select label="Edited" value={(draft.edited as string) ?? ""} onChange={(e) => set("edited")(e.target.value)} options={TRI} />
              <Select label="Creator not verified" value={(draft.unverified as string) ?? ""} onChange={(e) => set("unverified")(e.target.value)} options={TRI.slice(0, 2)} />
              <Select label="Had a refused attempt" value={(draft.failed_sync as string) ?? ""} onChange={(e) => set("failed_sync")(e.target.value)} options={TRI.slice(0, 2)} />
              <Select label="Same number sent again" value={(draft.duplicate_attempts as string) ?? ""} onChange={(e) => set("duplicate_attempts")(e.target.value)} options={TRI.slice(0, 2)} />
              {input("source", "Source (app, web, import...)")}
            </>
          )}
          {tab === "attempts" && (
            <Select label="Outcome" value={(draft.attempt_outcome as string) ?? ""} onChange={(e) => set("attempt_outcome")(e.target.value)}
              options={[{ value: "", label: "Any" }, { value: "saved", label: "Saved" }, { value: "rejected", label: "Refused" }, { value: "duplicate", label: "Same number sent again" }]} />
          )}
          <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-4">
            <Button type="submit">Search</Button>
            <Button type="button" variant="ghost" onClick={reset}>Clear filters</Button>
            {tab === "entries" && <Button type="button" variant="ghost" onClick={() => setMore((m) => !m)}>{more ? "Fewer filters" : "More filters"}</Button>}
          </div>
        </form>
      )}

      {(tab === "entries" || tab === "removed") && (
        <>
          {tab === "entries" && (employeeId || storeId) && (
            <Crumbs
              person={employeeId ? personName || "This employee" : undefined} store={storeId ? storeName || "One store" : undefined}
              onAll={() => { setPersonName(""); setStoreName(""); f.clearDrill("none"); }} onPerson={employeeId ? () => { setStoreName(""); f.clearDrill("employee"); } : undefined}
            />
          )}
          {showStores && <EmployeeStoresTable creatorId={employeeId} filters={applied} onOpenStore={(st) => { setStoreName(st.name); f.pick("store_id", st.id); }} />}
          {tab === "entries" && storeId && (
            <StoreReviewPanel
              scope={{ storeId, creatorId: employeeId || undefined, dateFrom: (applied.date_from as string) || undefined, dateTo: (applied.date_to as string) || undefined }}
              onOpenEntry={setOpen}
            />
          )}
          {!showStores && search.isLoading && <Skeleton className="h-64" />}
          {!showStores && search.isError && <ErrorState message={search.error instanceof Error ? search.error.message : "Couldn't search."} onRetry={() => search.refetch()} />}
          {!showStores && search.data && tab === "entries" && (
            <>
              <p className="flex flex-wrap items-center gap-x-3 text-sm text-gray-500">
                {storeId && <b className="text-gray-900">Entries audit</b>}
                {search.data.total.toLocaleString()} entr{search.data.total === 1 ? "y" : "ies"} found
                {storeId && employeeId && <button type="button" className="font-semibold text-brand-600 hover:underline" onClick={() => f.pick("creator_id", "")}>Show every employee's entries for this store</button>}
              </p>
              <EntryResultsTable byStore={Boolean(storeId)} rows={search.data.items} onOpen={setOpen} onPickStore={(st) => { setStoreName(st.name); f.pick("store_id", st.id); }} />
              <Pagination page={page} pageSize={search.data.page_size} total={search.data.total} onPageChange={setPage} />
            </>
          )}
          {!showStores && search.data && tab === "removed" && (
            <>
              <p className="text-sm text-gray-500">Entries that were removed. They are no longer on any report; their history is kept.</p>
              <Table>
                <thead><tr><Th>Store</Th><Th>Day</Th><Th>Number</Th><Th>Removed by</Th><Th>Removed (server time)</Th><Th className="text-right">History</Th></tr></thead>
                <tbody>
                  {search.data.items.length === 0 && <TableEmpty colSpan={6}>No removed entries match.</TableEmpty>}
                  {search.data.items.map((r) => (
                    <tr key={r.entry_id}>
                      <Td><span className="font-semibold text-gray-900">{r.store?.name ?? "(store deleted)"}</span><span className="block text-xs text-gray-500">{r.store?.outlet_id}</span></Td>
                      <Td>{fmtDay(r.order_date)}</Td>
                      <Td className="font-bold tabular-nums">{r.employee_count ?? "—"}</Td>
                      <Td>{r.removed_by?.name ?? <Badge tone="warning">unknown</Badge>}<span className="block text-xs text-gray-500">{r.removed_by?.code}</span></Td>
                      <Td className="text-xs">{fmtMoment(r.removed_at)}</Td>
                      <Td className="text-right"><Button size="sm" variant="secondary" onClick={() => setOpen(r.entry_id)}>Open</Button></Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <Pagination page={page} pageSize={search.data.page_size} total={search.data.total} onPageChange={setPage} />
            </>
          )}
        </>
      )}

      {tab === "attempts" && (
        <>
          {attempts.isLoading && <Skeleton className="h-64" />}
          {attempts.data && (
            <>
              <p className="text-sm text-gray-500">Every try to mark an entry is kept here, whether or not it was saved. Refused tries are the ones a person may remember as "I entered it".</p>
              <Table>
                <thead><tr><Th>When (IST)</Th><Th>Person</Th><Th>Store</Th><Th>Day</Th><Th>Number tried</Th><Th>Outcome</Th><Th>Where from</Th></tr></thead>
                <tbody>
                  {attempts.data.items.length === 0 && <TableEmpty colSpan={7}>Nothing matches.</TableEmpty>}
                  {attempts.data.items.map((a) => (
                    <tr key={a.id}>
                      <Td className="whitespace-nowrap text-xs">{fmtMoment(a.created_at)}</Td>
                      <Td>{a.user_name ?? "unknown"}<span className="block text-xs text-gray-500">{a.user_code}</span></Td>
                      <Td>{a.store_name ?? "—"}<span className="block text-xs text-gray-500">{a.outlet_id}</span></Td>
                      <Td className="whitespace-nowrap">{fmtDay(a.order_date)}</Td>
                      <Td className="font-bold tabular-nums">{a.bottle_count ?? "—"}</Td>
                      <Td>
                        <Badge tone={a.outcome === "saved" ? "success" : a.outcome === "duplicate" ? "info" : "danger"}>{a.outcome === "duplicate" ? "same number again" : a.outcome === "rejected" ? "refused" : "saved"}</Badge>
                        {a.reason && <span className="block text-xs text-gray-500">{a.reason}</span>}
                      </Td>
                      <Td className="text-xs text-gray-500">{a.client ?? "—"}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <Pagination page={page} pageSize={25} total={attempts.data.total} onPageChange={setPage} />
            </>
          )}
        </>
      )}

      {tab === "security" && (
        <>
          <div className="max-w-xs">
            <Select label="Type" value={secType} onChange={(e) => { setSecType(e.target.value); setPage(1); }}
              options={[{ value: "", label: "All" }, { value: "entry_access_denied", label: "Entry outside someone's scope" }, { value: "role_change", label: "Role or team changes" }, { value: "role_change_denied", label: "Refused role changes" }, { value: "entry_edit_denied", label: "Refused corrections" }, { value: "entry_search_denied", label: "Refused searches" }]} />
          </div>
          {security.isLoading && <Skeleton className="h-64" />}
          {security.data && (
            <>
              <Table>
                <thead><tr><Th>When (IST)</Th><Th>Person</Th><Th>What</Th><Th>About</Th><Th>Detail</Th></tr></thead>
                <tbody>
                  {security.data.items.length === 0 && <TableEmpty colSpan={5}>Nothing recorded.</TableEmpty>}
                  {security.data.items.map((s) => (
                    <tr key={s.id}>
                      <Td className="whitespace-nowrap text-xs">{fmtMoment(s.created_at)}</Td>
                      <Td>{s.actor_name ?? "—"}<span className="block text-xs text-gray-500">{s.actor_code}</span></Td>
                      <Td><Badge tone="warning">{s.event_type.replaceAll("_", " ")}</Badge></Td>
                      <Td className="text-xs text-gray-500">{s.target_type} {s.target_id?.slice(0, 8)}</Td>
                      <Td className="max-w-xs break-words text-xs text-gray-600">{s.detail ? JSON.stringify(s.detail) : ""}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <Pagination page={page} pageSize={25} total={security.data.total} onPageChange={setPage} />
            </>
          )}
        </>
      )}

      {open && <EntryDrawer entryId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
