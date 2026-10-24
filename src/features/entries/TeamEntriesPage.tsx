import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useEntrySearch } from "@/features/entries/api";
import { EntryDrawer } from "@/features/entries/EntryDrawer";
import { EntryPicker, StatusChips } from "@/features/entries/EntryFilters";
import { EntryResultsTable } from "@/features/entries/EntryResultsTable";
import { STATUS_FILTER_OPTIONS } from "@/features/entries/format";
import { useEntryFilters } from "@/features/entries/useEntryFilters";

/**
 * Entries to Verify (Level 2, Team Lead): the entries of the people who report to you, starting on the ones still waiting for you. Filter by store, employee,
 * date and status; open a date to verify it, correct it (a correction also verifies it) or comment. A Reviewer's "please check this" requests show up here.
 */
export function TeamEntriesPage() {
  const f = useEntryFilters("pending_l2");
  const [open, setOpen] = useState<string | null>(null);
  const [storeName, setStoreName] = useState("");
  const search = useEntrySearch(f.applied, f.page);
  const status = (f.draft.verification as string) ?? "";

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Entries to Verify" subtitle="Entries entered by you and the people who report to you. Verify what is right, or correct a mistake (a reason is required); the original value and who entered it are always kept." />
      <StatusChips active={status} onPick={f.chooseStatus} />

      <form className="grid gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => { e.preventDefault(); f.search(); }}>
        <EntryPicker kind="store" label="Store" placeholder="Search a store…" value={(f.draft.store_id as string) ?? ""} valueLabel={storeName} onPick={(id, label) => { setStoreName(label ?? ""); f.pick("store_id", id); }} />
        <EntryPicker kind="person" label="Employee" placeholder="Search an employee…" value={(f.draft.creator_id as string) ?? ""} onPick={(id) => f.pick("creator_id", id)} />
        <Select label="Status" value={status} onChange={(e) => f.chooseStatus(e.target.value)} options={STATUS_FILTER_OPTIONS} />
        <Input label="Store name, code or outlet" value={(f.draft.store as string) ?? ""} onChange={(e) => f.set("store")(e.target.value)} placeholder="Type, then Search" />
        <Input label="Day from" type="date" value={(f.draft.date_from as string) ?? ""} onChange={(e) => f.set("date_from")(e.target.value)} />
        <Input label="Day to" type="date" value={(f.draft.date_to as string) ?? ""} onChange={(e) => f.set("date_to")(e.target.value)} />
        <Select label="Edited" value={(f.draft.edited as string) ?? ""} onChange={(e) => f.set("edited")(e.target.value)} options={[{ value: "", label: "Any" }, { value: "true", label: "Yes" }, { value: "false", label: "No" }]} />
        <div className="flex items-end gap-2">
          <Button type="submit">Search</Button>
          <Button type="button" variant="ghost" onClick={() => { setStoreName(""); f.reset(); }}>Clear filters</Button>
        </div>
      </form>

      {search.isLoading && <Skeleton className="h-64" />}
      {search.isError && <ErrorState message={search.error instanceof Error ? search.error.message : "Couldn't load the entries."} onRetry={() => search.refetch()} />}
      {search.data && (
        <>
          {f.applied.store_id && (
            <p className="flex flex-wrap items-center gap-2 rounded-xl bg-brand-500/8 px-3.5 py-2 text-sm text-gray-800">
              Showing <b>{storeName || "one store"}</b>, date by date. Click a date to open it.
              <button type="button" className="font-semibold text-brand-600 hover:underline" onClick={() => f.pick("store_id", "")}>Show every store</button>
            </p>
          )}
          <p className="text-sm text-gray-500">{search.data.total.toLocaleString()} entr{search.data.total === 1 ? "y" : "ies"}</p>
          <EntryResultsTable rows={search.data.items} onOpen={setOpen} onPickStore={(s) => { setStoreName(s.name); f.pick("store_id", s.id); }} />
          <Pagination page={f.page} pageSize={search.data.page_size} total={search.data.total} onPageChange={f.setPage} />
        </>
      )}
      {open && <EntryDrawer entryId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
