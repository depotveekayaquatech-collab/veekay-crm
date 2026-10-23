import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useEntrySearch, useTeamMembers, type Filters } from "@/features/entries/api";
import { EntryHistoryModal } from "@/features/entries/EntryHistoryModal";
import { EntryResultsTable } from "@/features/entries/EntryResultsTable";

/** Team Lead: the entries of the people who report to you (and your own). Open one to see its history or correct it with a reason. */
export function TeamEntriesPage() {
  const team = useTeamMembers(true);
  const [draft, setDraft] = useState<Filters>({});
  const [applied, setApplied] = useState<Filters>({});
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const search = useEntrySearch(applied, page);

  const set = (k: string) => (v: string) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Team entries" subtitle="Entries entered by you and the people who report to you. You can correct a mistake (a reason is required); the original value and who entered it are always kept." />
      <form className="grid gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => { e.preventDefault(); setApplied(draft); setPage(1); }}>
        <Input label="Store name, code or outlet" value={(draft.store as string) ?? ""} onChange={(e) => set("store")(e.target.value)} />
        <Select label="Team member" value={(draft.creator_id as string) ?? ""} onChange={(e) => set("creator_id")(e.target.value)}
          options={[{ value: "", label: "Everyone" }, ...(team.data ?? []).map((m) => ({ value: m.id, label: `${m.name} (${m.code})${m.is_me ? " · you" : ""}` }))]} />
        <Input label="Day from" type="date" value={(draft.date_from as string) ?? ""} onChange={(e) => set("date_from")(e.target.value)} />
        <Input label="Day to" type="date" value={(draft.date_to as string) ?? ""} onChange={(e) => set("date_to")(e.target.value)} />
        <Select label="Edited" value={(draft.edited as string) ?? ""} onChange={(e) => set("edited")(e.target.value)} options={[{ value: "", label: "Any" }, { value: "true", label: "Yes" }, { value: "false", label: "No" }]} />
        <Select label="Flagged by a reviewer" value={(draft.flagged as string) ?? ""} onChange={(e) => set("flagged")(e.target.value)} options={[{ value: "", label: "Any" }, { value: "true", label: "Yes" }]} />
        <div className="flex items-end gap-2 sm:col-span-2">
          <Button type="submit">Search</Button>
          <Button type="button" variant="ghost" onClick={() => { setDraft({}); setApplied({}); setPage(1); }}>Clear filters</Button>
        </div>
      </form>

      {search.isLoading && <Skeleton className="h-64" />}
      {search.isError && <ErrorState message={search.error instanceof Error ? search.error.message : "Couldn't load the entries."} onRetry={() => search.refetch()} />}
      {search.data && (
        <>
          <p className="text-sm text-gray-500">{search.data.total.toLocaleString()} entr{search.data.total === 1 ? "y" : "ies"}</p>
          <EntryResultsTable rows={search.data.items} onOpen={setOpen} />
          <Pagination page={page} pageSize={search.data.page_size} total={search.data.total} onPageChange={setPage} />
        </>
      )}
      {open && <EntryHistoryModal entryId={open} onClose={() => setOpen(null)} canEdit canReview={false} />}
    </div>
  );
}
