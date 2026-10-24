/** The operation runs on Indian time; the server stores UTC. Every audit screen shows date, time AND the zone, so nothing is ambiguous. */
const ZONE = "Asia/Kolkata";
const ZONE_LABEL = "IST";

export function fmtMoment(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const date = d.toLocaleDateString("en-IN", { timeZone: ZONE, day: "2-digit", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString("en-IN", { timeZone: ZONE, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  return `${date}, ${time} ${ZONE_LABEL}`;
}

export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export const ROLE_LABEL: Record<string, string> = {
  entry_contributor: "Data Entry",
  team_lead: "Team Lead",
  entry_reviewer: "Reviewer",
  administrator: "Administrator",
  developer: "Developer",
  custom_admin: "Admin (custom)",
  accountant: "Accounts",
  partner: "Partner",
  unknown: "Unknown",
};

export const roleLabel = (role: string | null | undefined): string => (role ? ROLE_LABEL[role] ?? role : "—");

export const EVENT_LABEL: Record<string, string> = {
  CREATED: "Created",
  BASELINE: "Existing entry (history starts here)",
  EDITED: "Edited",
  CLEARED: "Removed",
  RESTORED: "Restored",
  VERIFIED_L2: "Verified by Team Lead",
  REVIEWED_L3: "Reviewed by Reviewer",
  CHECK_REQUESTED: "Verification requested",
  COMMENTED: "Comment",
  REVIEWED: "Reviewed",
  FLAGGED: "Flagged",
  NEEDS_CORRECTION: "Marked as needing correction",
  STATUS_CHANGED: "Review mark cleared",
};

export const FLAG_LABEL: Record<string, string> = {
  edited: "Edited",
  unverified_creator: "Creator not verified",
  flagged: "Flagged",
  needs_correction: "Needs correction",
  zero_count: "Zero count",
  unusually_high: "Unusually high",
  entered_late: "Entered days late",
};

export const FIELD_LABEL: Record<string, string> = {
  bottle_count: "Bottles (final)",
  cash_adjustment: "Cash adjustment",
  source: "Source",
  store_id: "Store",
  order_date: "Date",
  review_status: "Review",
  verification_status: "Status",
  last_recorded_marker: "Last recorded marker",
};

export function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}

/** The verification workflow. `Submitted (L1)` -> `Verified by Team Lead (L2)` -> `Reviewed by Reviewer (L3)`. */
export type Verification = "submitted" | "verified_l2" | "reviewed_l3";

export const VERIFICATION_LABEL: Record<Verification, string> = {
  submitted: "Submitted (L1)",
  verified_l2: "Verified by Team Lead (L2)",
  reviewed_l3: "Reviewed by Reviewer (L3)",
};
export const VERIFICATION_SHORT: Record<Verification, string> = { submitted: "Submitted", verified_l2: "Verified by Team Lead", reviewed_l3: "Reviewed by Reviewer" };
export const VERIFICATION_TONE: Record<Verification, "warning" | "info" | "success"> = { submitted: "warning", verified_l2: "info", reviewed_l3: "success" };

/** The status filter shared by the Team Lead and Reviewer screens (the values are the API's `verification` parameter). */
export const STATUS_FILTER_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "pending_l2", label: "Pending Team Lead (L2)" },
  { value: "verified_l2", label: "Verified by Team Lead (L2)" },
  { value: "reviewed_l3", label: "Reviewed by Reviewer (L3)" },
  { value: "requested", label: "Verification requested" },
];

/** "24 Oct 2026, 4:10 PM": the wording Level 1 sees next to "Changed by Rahul - Team Lead". */
export function fmtMomentShort(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const date = d.toLocaleDateString("en-IN", { timeZone: ZONE, day: "numeric", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString("en-IN", { timeZone: ZONE, hour: "numeric", minute: "2-digit", hour12: true }).toUpperCase();
  return `${date}, ${time}`;
}
