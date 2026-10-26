import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";
import type { Verification } from "@/features/entries/format";

/* The audit endpoints are used as the server sends them (snake_case): the values inside an event's old / new are the entry's own field names. */

export interface Person {
  id: string | null;
  name: string | null;
  code?: string | null;
  role: string | null;
}

/** Where an entry stands in the Submitted -> Verified by Team Lead -> Reviewed by Reviewer workflow, and who did each step. */
export interface VerificationInfo {
  status: Verification;
  label: string;
  verified_by: { id: string; name: string | null; at: string | null } | null;
  reviewed_by: { id: string; name: string | null; at: string | null } | null;
  /** An open "please check this" request from a Reviewer to the Team Lead. */
  check_requested: { by_id: string | null; by_name: string | null; at: string; note: string | null } | null;
}

/** What the caller may do with this entry right now (the server enforces the same rules on every action). */
export interface EntryActions {
  edit: boolean;
  verify: boolean;
  review: boolean;
  request_check: boolean;
  flag: boolean;
  comment: boolean;
}

export interface EntryRow {
  entry_id: string;
  version: number;
  store: { id: string; name: string; crm_code: string | null; outlet_id: string; status: string; platform: string | null; platform_slug: string | null; entity?: string | null } | null;
  order_date: string | null;
  /** The employee's own number (a developer's cash adjustment is not part of it). */
  employee_count: number | null;
  /** Reviewers / administrators only: the final figure and the adjustment on top. */
  bottle_count: number | null;
  cash_adjustment: number | null;
  source: string;
  creator?: {
    id: string | null; name: string | null; code: string | null; role: string | null; verified: boolean; via: string | null;
    last_recorded_marker: string | null;
  };
  created_at?: string;
  client_submitted_at?: string | null;
  last_modified?: { by_id: string | null; by_name: string | null; role: string | null; at: string } | null;
  review?: { status: "none" | "reviewed" | "flagged" | "needs_correction"; by_id: string | null; at: string | null };
  verification?: VerificationInfo;
  actions?: EntryActions;
  source_app?: string | null;
  request_id?: string | null;
  flags?: string[];
  can_edit?: boolean;
  // removed entries
  cleared?: boolean;
  removed_at?: string;
  removed_by?: Person;
  reason?: string | null;
}

export interface SearchResult {
  total: number;
  page: number;
  page_size: number;
  level: string;
  items: EntryRow[];
}

export interface TimelineEvent {
  id: string;
  seq: number;
  type: string;
  at: string;
  actor: Person & { known: boolean };
  old: Record<string, unknown> | null;
  new: Record<string, unknown> | null;
  changed_fields: string[] | null;
  reason: string | null;
  comment: string | null;
  request_id: string | null;
  source: string | null;
  version: number | null;
}

export interface Attempt {
  created_at: string;
  outcome: "saved" | "rejected" | "duplicate";
  reason: string | null;
  bottle_count: number | null;
  action: string;
  request_key: string | null;
  client: string | null;
  user_name: string | null;
  user_code: string | null;
}

export interface Timeline {
  entry_id: string;
  removed: boolean;
  chain_ok: boolean;
  level: string;
  store: { id: string; name: string; crm_code: string | null; outlet_id: string; entity?: string | null } | null;
  events: TimelineEvent[];
  attempts: Attempt[];
  display_timezone: string;
  entry?: EntryRow;
  /** Only on the answer to "request check": who was notified. */
  request?: { already_open: boolean; team_lead?: { id: string; name: string } | null };
}

export type Filters = Record<string, string | boolean | undefined>;

export function toQuery(filters: Filters, extra: Record<string, string | number>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === "" || v === false) continue;
    qs.set(k, String(v));
  }
  for (const [k, v] of Object.entries(extra)) qs.set(k, String(v));
  return qs.toString();
}

// Audit data is never kept after the screen is left (gcTime 0) and never shown stale.
export function useEntrySearch(filters: Filters, page: number, pageSize = 25, enabled = true) {
  return useQuery({
    enabled,
    queryKey: ["entry-search", filters, page, pageSize],
    queryFn: () => apiRequest<SearchResult>(`/entries/search?${toQuery(filters, { page, page_size: pageSize })}`, { silent: true }),
    placeholderData: keepPreviousData,
    gcTime: 0,
    staleTime: 0,
  });
}

export function useTimeline(entryId: string | null) {
  return useQuery({
    queryKey: ["entry-timeline", entryId],
    queryFn: () => apiRequest<Timeline>(`/entries/${entryId}`, { silent: true }),
    enabled: Boolean(entryId),
    gcTime: 0,
    staleTime: 0,
  });
}

export function useAttempts(filters: Filters, page: number, enabled: boolean) {
  return useQuery({
    queryKey: ["entry-attempts", filters, page],
    queryFn: () =>
      apiRequest<{ total: number; items: (Attempt & { id: string; order_date: string; store_name: string | null; crm_code: string | null; outlet_id: string | null })[] }>(
        `/entries/attempts?${toQuery(filters, { page, page_size: 25 })}`, { silent: true }),
    enabled,
    placeholderData: keepPreviousData,
    gcTime: 0,
  });
}

export function useSecurityEvents(type: string, page: number, enabled: boolean) {
  return useQuery({
    queryKey: ["entry-security", type, page],
    queryFn: () =>
      apiRequest<{ total: number; items: { id: string; created_at: string; actor_name: string | null; actor_code: string | null; actor_role: string | null; event_type: string; target_type: string | null; target_id: string | null; detail: Record<string, unknown> | null; ip: string | null }[] }>(
        `/entries/security-events?${toQuery({ event_type: type }, { page, page_size: 25 })}`, { silent: true }),
    enabled,
    placeholderData: keepPreviousData,
    gcTime: 0,
  });
}

export function useTeamMembers(enabled: boolean) {
  return useQuery({ queryKey: ["entry-team"], queryFn: () => apiRequest<{ id: string; name: string; code: string; is_me: boolean }[]>("/entries/team", { silent: true }), enabled });
}

export interface StoreOption { id: string; name: string; code: string; crm_code: string | null; platform: string; status: string }
export interface PersonOption { id: string; name: string; code: string; is_me: boolean }

/** Server-side typeahead for the Store-wise and Employee-wise filters (always inside the caller's own scope, so it stays fast on any list size). */
export function useFilterOptions<K extends "store" | "person">(kind: K, q: string, enabled = true, platformId = "") {
  return useQuery({
    enabled,
    queryKey: ["entry-options", kind, q, platformId],
    // employees: the whole list of a partner fits one dropdown (up to 300); stores stay a 20-best-matches typeahead
    queryFn: () => apiRequest<(K extends "store" ? StoreOption : PersonOption)[]>(`/entries/options?${toQuery({ kind, q, platform_id: platformId }, { limit: kind === "person" ? 300 : 20 })}`, { silent: true }),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export interface PlatformOption { id: string; name: string; slug: string }

/** The partners (Blinkit, Zepto ...) the caller can look into. One entry means the dropdown is not needed (a Blinkit Reviewer sees only Blinkit). */
export function usePlatforms() {
  return useQuery({ queryKey: ["entry-platforms"], queryFn: () => apiRequest<PlatformOption[]>("/entries/options?kind=platform", { silent: true }), staleTime: 5 * 60_000 });
}

export interface StoreOfEmployee {
  store: { id: string; name: string; crm_code: string | null; outlet_id: string; status: string; entity: string | null; platform: string };
  entries: number;
  pending_l2: number;
  verified_l2: number;
  reviewed_l3: number;
  requested: number;
  bottles: number;
  last_entry: string | null;
}

/** The stores one employee has entered, with how many of their entries are in each state: the step between choosing an employee and opening a store's entries. */
export function useEmployeeStores(creatorId: string, filters: Filters) {
  return useQuery({
    queryKey: ["entry-employee-stores", creatorId, filters.date_from, filters.date_to, filters.verification],
    queryFn: () =>
      apiRequest<{ employee: { id: string; name: string; code: string }; level: string; verify_to: Verification | null; total: number; items: StoreOfEmployee[] }>(
        `/entries/employee-stores?${toQuery({ creator_id: creatorId, date_from: filters.date_from, date_to: filters.date_to, verification: filters.verification }, {})}`, { silent: true }),
    enabled: Boolean(creatorId),
    gcTime: 0,
    staleTime: 0,
  });
}

export interface StoreReviewDay {
  date: string;
  day: number;
  is_future: boolean;
  is_today: boolean;
  entry: { entry_id: string; count: number; status: Verification; requested: boolean; flagged: boolean; edited: boolean; created_by: string | null } | null;
}

/** One store opened for checking: its details, a month of its entries, the counts per state, and what one click on "Verify store" would change. */
export interface StoreReview {
  store: {
    id: string; name: string; outlet_id: string; crm_code: string | null; entity: string | null; status: string; city: string | null; state: string | null;
    region_name: string | null; platform: string | null; platform_slug: string | null; poc_name: string | null; poc_number: string | null; vendor_name: string | null; vendor_number: string | null;
  };
  year: number;
  month: number;
  days: StoreReviewDay[];
  level: string;
  counts: { entries: number; pending_l2: number; verified_l2: number; reviewed_l3: number; requested: number; flagged: number };
  verify: { allowed: boolean; to: Verification; will_change: number; skipped_flagged: number };
}

export interface StoreReviewScope { storeId: string; creatorId?: string; dateFrom?: string; dateTo?: string }

export function useStoreReview(scope: StoreReviewScope, period: { year?: number; month?: number }) {
  return useQuery({
    queryKey: ["entry-store-review", scope, period],
    queryFn: () => apiRequest<StoreReview>(
      `/entries/store-review?${toQuery({ store_id: scope.storeId, creator_id: scope.creatorId, date_from: scope.dateFrom, date_to: scope.dateTo }, { ...(period.year ? { year: period.year } : {}), ...(period.month ? { month: period.month } : {}) })}`,
      { silent: true }),
    gcTime: 0,
    staleTime: 0,
  });
}

/** "I checked this store": every entry in view is verified (Team Lead) or reviewed (Reviewer / administrator) in one step, not one by one. */
export function useVerifyStore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: StoreReviewScope & { comment?: string }) =>
      apiRequest<{ changed: number; to: Verification; skipped_flagged: number }>("/entries/verify-store", {
        method: "POST", silent: true,
        body: { store_id: v.storeId, creator_id: v.creatorId || null, date_from: v.dateFrom || null, date_to: v.dateTo || null, comment: v.comment || null },
      }),
    onSuccess: (r) => {
      const what = r.to === "reviewed_l3" ? "reviewed" : "verified";
      pushToast(r.changed === 0 ? "Nothing to verify here." : `${r.changed} entr${r.changed === 1 ? "y" : "ies"} ${what}.${r.skipped_flagged ? ` ${r.skipped_flagged} flagged left for you to look at.` : ""}`, r.changed === 0 ? "info" : "success");
      for (const key of ["entry-store-review", "entry-search", "entry-summary", "entry-employee-stores", "entry-timeline", "entry-team-overview"]) void qc.invalidateQueries({ queryKey: [key] });
    },
  });
}

export interface TeamOverview {
  month_start: string;
  today: string;
  members: number;
  stores: number;
  entries: number;
  bottles: number;
  today_entries: number;
  today_bottles: number;
  pending_l2: number;
  verified_l2: number;
  reviewed_l3: number;
  requested: number;
  not_entered_today: number;
  people: { id: string; name: string; code: string; is_me: boolean; entries: number; stores: number; bottles: number; pending_l2: number; verified_l2: number; reviewed_l3: number; requested: number; last_entry: string | null; today_entries: number; today_bottles: number }[];
}

/** The Team Lead's dashboard numbers (this month and today, for the whole team). */
export function useTeamOverview(enabled = true) {
  return useQuery({ queryKey: ["entry-team-overview"], queryFn: () => apiRequest<TeamOverview>("/entries/team-overview", { silent: true }), enabled, staleTime: 30_000, refetchInterval: 120_000 });
}

export interface EntrySummary { since: string; days: number; pending_l2: number; verified_l2: number; reviewed_l3: number; requested: number }

export function useEntrySummary(enabled = true) {
  return useQuery({
    queryKey: ["entry-summary"],
    queryFn: () => apiRequest<EntrySummary>("/entries/summary", { silent: true }),
    enabled,
    staleTime: 15_000,
    refetchInterval: 60_000,
  });
}

/** After an action the drawer shows the server's answer and the table row changes with it, without a reload; the counters and lists refresh in the background. */
function applyToLists(qc: QueryClient, t: Timeline) {
  qc.setQueryData(["entry-timeline", t.entry_id], t);
  if (t.entry) {
    const fresh = t.entry;
    qc.setQueriesData<SearchResult>({ queryKey: ["entry-search"] }, (old) =>
      old ? { ...old, items: old.items.map((r) => (r.entry_id === fresh.entry_id ? { ...r, ...fresh } : r)) } : old);
  }
  void qc.invalidateQueries({ queryKey: ["entry-search"] });
  void qc.invalidateQueries({ queryKey: ["entry-summary"] });
  void qc.invalidateQueries({ queryKey: ["entry-store-review"] });
}

export function useEditEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { entryId: string; bottleCount: number; reason: string; expectedVersion: number }) =>
      apiRequest<Timeline>(`/entries/${v.entryId}`, {
        method: "PATCH", silent: true,
        body: { bottle_count: v.bottleCount, reason: v.reason, expected_version: v.expectedVersion },
      }),
    onSuccess: (t) => {
      pushToast("Entry corrected. The change and your reason are in its history.", "success");
      applyToLists(qc, t);
    },
    // a 409 means somebody changed it first: show the newest version
    onError: () => void qc.invalidateQueries({ queryKey: ["entry-timeline"] }),
  });
}

export function useReviewEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { entryId: string; action: "reviewed" | "flagged" | "needs_correction" | "clear"; comment?: string }) =>
      apiRequest<Timeline>(`/entries/${v.entryId}/review`, { method: "POST", silent: true, body: { action: v.action, comment: v.comment || null } }),
    onSuccess: (t, v) => {
      if (v.action === "reviewed") pushToast("Marked as reviewed. It is final: the Team Lead no longer needs to verify it.", "success");
      applyToLists(qc, t);
    },
    onError: () => void qc.invalidateQueries({ queryKey: ["entry-timeline"] }),
  });
}

export function useVerifyEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { entryId: string; comment?: string }) =>
      apiRequest<Timeline>(`/entries/${v.entryId}/verify`, { method: "POST", silent: true, body: { comment: v.comment || null } }),
    onSuccess: (t) => {
      pushToast("Verified. The Reviewer can now see it as ready to review.", "success");
      applyToLists(qc, t);
    },
    onError: () => void qc.invalidateQueries({ queryKey: ["entry-timeline"] }),
  });
}

export function useRequestCheck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { entryId: string; note?: string }) =>
      apiRequest<Timeline>(`/entries/${v.entryId}/request-check`, { method: "POST", silent: true, body: { note: v.note || null } }),
    onSuccess: (t) => {
      const lead = t.request?.team_lead?.name;
      pushToast(
        t.request?.already_open ? "A check was already requested."
          : lead ? `Request sent. ${lead} will see it in their pending list.`
          : "Request recorded, but this person has no Team Lead assigned, so nobody was notified.",
        lead || t.request?.already_open ? "success" : "info",
      );
      applyToLists(qc, t);
    },
    onError: () => void qc.invalidateQueries({ queryKey: ["entry-timeline"] }),
  });
}

export function useAddComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { entryId: string; text: string }) =>
      apiRequest<Timeline>(`/entries/${v.entryId}/comments`, { method: "POST", silent: true, body: { text: v.text } }),
    onSuccess: (t) => applyToLists(qc, t),
  });
}
