import { useState } from "react";
import type { Filters } from "@/features/entries/api";

/**
 * The filter state shared by the Team Lead and Reviewer screens. Store, employee and status apply the moment they are chosen (they are picks, not typing);
 * the free-text and date fields apply with Search. A screen starts on its own work queue (Team Lead: pending, Reviewer: ready to review), but the moment a
 * person looks up one store the status filter opens to "all statuses", unless they chose a status themselves: searching a store must find its entries
 * whatever their state (a Reviewer needs to see the ones the Team Lead has not verified yet).
 */
export function useEntryFilters(defaultStatus: string) {
  const start: Filters = { verification: defaultStatus };
  const [draft, setDraft] = useState<Filters>(start);
  const [applied, setApplied] = useState<Filters>(start);
  const [statusChosen, setStatusChosen] = useState(false);
  const [page, setPage] = useState(1);

  const commit = (next: Filters, chosen = statusChosen) => {
    const lookingUpAStore = Boolean(next.store_id || (typeof next.store === "string" && next.store.trim()));
    const out = lookingUpAStore && !chosen ? { ...next, verification: "" } : next;
    setDraft(out);
    setApplied(out);
    setPage(1);
  };

  return {
    draft, applied, page, setPage,
    /** Edit a free-text / date field (applied by Search). */
    set: (k: string) => (v: string) => setDraft((d) => ({ ...d, [k]: v })),
    /** Choose a store or an employee (applied at once). */
    pick: (k: "store_id" | "creator_id", v: string) => commit({ ...draft, [k]: v, ...(k === "store_id" ? { store: "" } : {}) }),
    chooseStatus: (v: string) => { setStatusChosen(true); commit({ ...draft, verification: v }, true); },
    search: () => commit(draft),
    reset: () => { setStatusChosen(false); setDraft(start); setApplied(start); setPage(1); },
    isDefault: (f: Filters) => Object.entries(f).every(([k, v]) => (k === "verification" ? v === defaultStatus : !v)),
  };
}
