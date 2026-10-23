import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";

/* The audit endpoints are used as the server sends them (snake_case): the values inside an event's old / new are the entry's own field names. */

export interface Person {
  id: string | null;
  name: string | null;
  code?: string | null;
  role: string | null;
}

export interface EntryRow {
  entry_id: string;
  version: number;
  store: { id: string; name: string; crm_code: string | null; outlet_id: string; status: string; platform: string | null; platform_slug: string | null } | null;
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
  store: { id: string; name: string; crm_code: string | null; outlet_id: string } | null;
  events: TimelineEvent[];
  attempts: Attempt[];
  display_timezone: string;
  entry?: EntryRow;
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
export function useEntrySearch(filters: Filters, page: number, pageSize = 25) {
  return useQuery({
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

export function useEditEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { entryId: string; bottleCount: number; reason: string; expectedVersion: number }) =>
      apiRequest<Timeline>(`/entries/${v.entryId}`, {
        method: "PATCH", silent: true,
        body: { bottle_count: v.bottleCount, reason: v.reason, expected_version: v.expectedVersion },
      }),
    onSuccess: () => {
      pushToast("Entry corrected. The change and your reason are in its history.", "success");
      void qc.invalidateQueries({ queryKey: ["entry-search"] });
      void qc.invalidateQueries({ queryKey: ["entry-timeline"] });
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
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["entry-search"] });
      void qc.invalidateQueries({ queryKey: ["entry-timeline"] });
    },
  });
}
