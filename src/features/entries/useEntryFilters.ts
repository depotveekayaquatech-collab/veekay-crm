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
    const lookingSomeoneUp = Boolean(next.store_id || next.creator_id || (typeof next.store === "string" && next.store.trim()));
    // looking someone up opens the status filter to "all"; going back to the full list returns to the work queue (unless a status was chosen on purpose)
    const out = chosen ? next : { ...next, verification: lookingSomeoneUp ? "" : defaultStatus };
    setDraft(out);
    setApplied(out);
    setPage(1);
  };

  return {
    draft, applied, page, setPage,
    /** Edit a free-text / date field (applied by Search). */
    set: (k: string) => (v: string) => setDraft((d) => ({ ...d, [k]: v })),
    /** Choose a partner, an employee or a store (applied at once). A new partner clears the employee and store; a new employee clears the store. */
    pick: (k: "platform" | "store_id" | "creator_id", v: string) =>
      commit({
        ...draft, [k]: v,
        ...(k === "store_id" ? { store: "" } : {}),
        ...(k === "creator_id" ? { store_id: "", store: "" } : {}),
        ...(k === "platform" ? { creator_id: "", store_id: "", store: "" } : {}),
      }),
    /** Back up one step of the drill-down (employee -> stores -> entries) or all the way to the full list. */
    clearDrill: (keep: "none" | "employee") => commit({ ...draft, store_id: "", store: "", ...(keep === "none" ? { creator_id: "" } : {}) }),
    chooseStatus: (v: string) => { setStatusChosen(true); commit({ ...draft, verification: v }, true); },
    search: () => commit(draft),
    reset: () => { setStatusChosen(false); setDraft(start); setApplied(start); setPage(1); },
    isDefault: (f: Filters) => Object.entries(f).every(([k, v]) => (k === "verification" ? v === defaultStatus : !v)),
  };
}
