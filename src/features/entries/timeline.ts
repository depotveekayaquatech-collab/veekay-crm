import type { TimelineEvent } from "@/features/entries/api";
import { FIELD_LABEL, roleLabel, type Verification } from "@/features/entries/format";

/** One row of the drawer's "Status timeline": a version of the entry, in the order it happened. */
export interface TimelineItem {
  key: string;
  /** "Status 1", "Status 2" ... */
  n: number;
  /** What happened, in words ("Submitted", "Edited and verified by Team Lead"). */
  label: string;
  /** Where the entry stood after this step (colours the dot and the chip). */
  state: Verification | null;
  tone: "success" | "warning" | "danger" | "info" | "neutral";
  at: string;
  actor: TimelineEvent["actor"];
  /** old -> new values worth highlighting (empty for steps that did not change a value). */
  changes: { field: string; label: string; old: string | null; neu: string }[];
  reason: string | null;
  current: boolean;
}

export interface SystemComment {
  key: string;
  at: string;
  actor: TimelineEvent["actor"];
  text: string;
  /** A person's own comment (COMMENTED) rather than the system's record of an action. */
  mine: boolean;
}

const MERGE_WITHIN_MS = 3000;
const SHOWN = new Set(["BASELINE", "CREATED", "RESTORED", "EDITED", "VERIFIED_L2", "REVIEWED_L3", "CHECK_REQUESTED", "FLAGGED", "NEEDS_CORRECTION", "REVIEWED", "STATUS_CHANGED", "CLEARED"]);

const val = (v: unknown): string => (v === null || v === undefined ? "—" : String(v));
const STATE_AFTER: Record<string, Verification> = { VERIFIED_L2: "verified_l2", REVIEWED_L3: "reviewed_l3" };

/** Only what a person cares about: the number (and a cash adjustment when there is one). `source`, ids and the state columns are bookkeeping, and a store or date appears only when it MOVED. */
function changesOf(e: TimelineEvent): TimelineItem["changes"] {
  const moved = e.old !== null;
  const fields = (e.changed_fields ?? Object.keys(e.new ?? {})).filter((f) => {
    if (f === "bottle_count") return true;
    if (f === "cash_adjustment") return moved || Number(e.new?.[f] ?? 0) !== 0;
    return moved && (f === "store_id" || f === "order_date");
  });
  return fields.map((f) => ({ field: f, label: FIELD_LABEL[f] ?? f, old: e.old ? val(e.old[f]) : null, neu: val(e.new?.[f]) }));
}

/** Turns the append-only events into the drawer's timeline. An edit that also moved the state (a Team Lead's correction verifies it, a Reviewer's makes it final) is shown as ONE step. */
export function buildTimeline(events: TimelineEvent[], initialState: Verification = "submitted"): TimelineItem[] {
  const items: TimelineItem[] = [];
  let state: Verification | null = initialState;
  let lastEditAt = 0;
  for (const e of events) {
    if (!SHOWN.has(e.type)) continue;
    const at = new Date(e.at).getTime();
    const stepState = STATE_AFTER[e.type];
    const prev = items[items.length - 1];
    if (stepState && prev && prev.label.startsWith("Edited") && prev.actor.id === e.actor.id && at - lastEditAt <= MERGE_WITHIN_MS) {
      prev.label = `Edited and ${e.type === "VERIFIED_L2" ? "verified by Team Lead" : "reviewed by Reviewer"}`;
      prev.state = stepState;
      prev.tone = stepState === "verified_l2" ? "info" : "success";
      state = stepState;
      continue;
    }
    if (stepState) state = stepState;
    if (e.type === "STATUS_CHANGED" && (e.new as { verification_status?: Verification } | null)?.verification_status === "submitted") state = "submitted";
    const base: Omit<TimelineItem, "key" | "n" | "label" | "tone"> = { state, at: e.at, actor: e.actor, changes: changesOf(e), reason: e.reason ?? e.comment, current: false };
    const item = (label: string, tone: TimelineItem["tone"]): TimelineItem => ({ ...base, key: e.id, n: items.length + 1, label, tone });
    switch (e.type) {
      case "BASELINE": items.push(item("Existing entry (history starts here)", "neutral")); break;
      case "CREATED": case "RESTORED": items.push(item(e.type === "RESTORED" ? "Restored" : "Submitted", "warning")); break;
      case "EDITED": items.push(item("Edited", "warning")); lastEditAt = at; break;
      case "VERIFIED_L2": items.push(item("Verified by Team Lead", "info")); break;
      case "REVIEWED_L3": case "REVIEWED": items.push(item("Reviewed by Reviewer", "success")); break;
      case "CHECK_REQUESTED": items.push(item("Verification requested", "warning")); break;
      case "FLAGGED": items.push(item("Flagged", "danger")); break;
      case "NEEDS_CORRECTION": items.push(item("Marked as needing correction", "danger")); break;
      case "STATUS_CHANGED": items.push(item((e.new as { verification_status?: string } | null)?.verification_status === "submitted" ? "Back to Submitted (the number changed)" : "Review mark cleared", "neutral")); break;
      case "CLEARED": items.push(item("Removed", "danger")); break;
    }
  }
  const last = items[items.length - 1];
  if (last) last.current = true;
  return items;
}

const who = (a: TimelineEvent["actor"]) => (a.known ? `${a.name ?? "Someone"} (${roleLabel(a.role)})` : "A direct database change");

/** The system's sentence for every action, plus people's own comments: the drawer's Comments card. Newest first. */
export function buildComments(events: TimelineEvent[]): SystemComment[] {
  const out: SystemComment[] = [];
  for (const e of events) {
    const note = e.comment ?? e.reason;
    const withNote = (s: string) => (note ? `${s} "${note}"` : s);
    let text: string | null = null;
    switch (e.type) {
      case "COMMENTED": out.push({ key: e.id, at: e.at, actor: e.actor, text: e.comment ?? "", mine: true }); continue;
      case "BASELINE": case "CREATED": case "RESTORED":
        text = `${who(e.actor)} ${e.type === "CREATED" ? "submitted" : e.type === "RESTORED" ? "restored" : "recorded"} ${e.new?.bottle_count != null ? `${val(e.new.bottle_count)} bottles` : "this entry"}.`;
        break;
      case "EDITED": {
        const c = changesOf(e).find((x) => x.field === "bottle_count");
        text = withNote(`${who(e.actor)} changed ${c ? `the number from ${c.old} to ${c.neu}` : "this entry"}.`);
        break;
      }
      case "VERIFIED_L2": text = withNote(`${who(e.actor)} verified this entry.`); break;
      case "REVIEWED_L3": case "REVIEWED": text = withNote(`${who(e.actor)} reviewed this entry. It is final.`); break;
      case "CHECK_REQUESTED": text = withNote(`${who(e.actor)} asked the Team Lead to check this entry.`); break;
      case "FLAGGED": text = withNote(`${who(e.actor)} flagged this entry.`); break;
      case "NEEDS_CORRECTION": text = withNote(`${who(e.actor)} marked this entry as needing correction.`); break;
      case "STATUS_CHANGED": text = `${who(e.actor)} changed its status.`; break;
      case "CLEARED": text = withNote(`${who(e.actor)} removed this entry.`); break;
    }
    if (text) out.push({ key: e.id, at: e.at, actor: e.actor, text, mine: false });
  }
  return out.reverse();
}
