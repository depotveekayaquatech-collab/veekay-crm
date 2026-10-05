import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { IconCheckCircle, IconSearch } from "@/components/ui/icons";
import { useStoreSearch, useTicketMutations } from "@/features/tickets/useTickets";
import { CATEGORY_LABEL, PRIORITY_LABEL, type StoreBrief, type TicketCategory, type TicketPriority } from "@/types/ticket";

const CATEGORIES = Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }));
const PRIORITIES = Object.entries(PRIORITY_LABEL).map(([value, label]) => ({ value, label }));

export function NewTicketModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const { create } = useTicketMutations();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [store, setStore] = useState<StoreBrief | null>(null);
  const [category, setCategory] = useState<TicketCategory>("LATE_DELIVERY");
  const [priority, setPriority] = useState<TicketPriority>("MEDIUM");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setSearch(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);
  const { data: choices = [], isFetching } = useStoreSearch(search);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!store) return setError("Choose the store this ticket is about.");
    setError(null);
    try {
      const t = await create.mutateAsync({ storeId: store.id, category, priority, title: title.trim(), description: description.trim() });
      onCreated(t.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't raise the ticket.");
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Raise a ticket"
      description="It goes straight to the people who handle that store's region."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={create.isPending}>Cancel</Button>
          <Button type="submit" form="ticket-form" isLoading={create.isPending} disabled={!store || title.trim().length < 3}>Raise ticket</Button>
        </>
      }
    >
      <form id="ticket-form" onSubmit={submit} className="flex flex-col gap-4">
        <div>
          <p className="mb-1.5 text-sm font-medium text-gray-700">Store</p>
          {store ? (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-brand-200 bg-brand-50/60 px-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-gray-900">{store.name}</p>
                <p className="truncate text-xs text-gray-500">
                  {[store.code, store.city, store.regionName, store.platformName].filter(Boolean).join(" · ")}
                </p>
              </div>
              <button type="button" className="shrink-0 text-xs font-semibold text-brand-600 hover:text-brand-700" onClick={() => setStore(null)}>
                Change
              </button>
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-surface-border">
              <div className="relative border-b border-surface-border">
                <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search store name, code or city"
                  aria-label="Search stores"
                  className="h-10 w-full bg-surface pl-9 pr-3 text-sm outline-none placeholder:text-gray-400"
                />
              </div>
              <ul className="max-h-52 divide-y divide-surface-border overflow-y-auto">
                {choices.length === 0 && (
                  <li className="px-3 py-6 text-center text-sm text-gray-500">{isFetching ? "Searching…" : "No stores found."}</li>
                )}
                {choices.map((s) => (
                  <li key={s.id}>
                    <button type="button" onClick={() => setStore(s)} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-surface-subtle">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-gray-900">{s.name}</span>
                        <span className="block truncate text-xs text-gray-500">{[s.code, s.city, s.regionName].filter(Boolean).join(" · ")}</span>
                      </span>
                      <span className="shrink-0 text-xs text-gray-400">{s.platformName}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="What went wrong" value={category} onChange={(e) => setCategory(e.target.value as TicketCategory)} options={CATEGORIES} />
          <Select label="Priority" value={priority} onChange={(e) => setPriority(e.target.value as TicketPriority)} options={PRIORITIES} />
        </div>
        <Input label="Summary" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Delivery arrived 3 hours late" maxLength={160} required />
        <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
          Details
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            maxLength={4000}
            placeholder="Optional — what happened, which delivery, who you spoke to"
            className="rounded-md border border-surface-border bg-surface px-3 py-2 text-sm font-normal shadow-sm outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </label>
        <p className="flex items-center gap-1.5 text-xs text-gray-500">
          <IconCheckCircle className="h-3.5 w-3.5 text-status-success" />
          Urgent tickets are expected to be resolved in 12 hours, high in 24, medium in 48, low in 96.
        </p>
        {error && <p className="text-sm text-status-danger">{error}</p>}
      </form>
    </Modal>
  );
}
