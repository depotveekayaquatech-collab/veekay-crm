import { describe, expect, it } from "vitest";
import type { TimelineEvent } from "@/features/entries/api";
import { buildComments, buildTimeline } from "@/features/entries/timeline";

let n = 0;
const ev = (type: string, at: string, who: { id: string; name: string; role: string }, extra: Partial<TimelineEvent> = {}): TimelineEvent => ({
  id: `e${++n}`, seq: n, type, at, actor: { ...who, known: true }, old: null, new: null, changed_fields: null, reason: null, comment: null,
  request_id: null, source: null, version: 1, ...extra,
});
const A = { id: "a", name: "Asha", role: "entry_contributor" };
const L = { id: "l", name: "Rahul", role: "team_lead" };
const R = { id: "r", name: "Meera", role: "entry_reviewer" };

describe("the verification timeline", () => {
  it("numbers each version and marks the last one as current", () => {
    const items = buildTimeline([
      ev("CREATED", "2026-10-24T09:00:00Z", A, { new: { bottle_count: 11 } }),
      ev("VERIFIED_L2", "2026-10-24T10:00:00Z", L, { new: { verification_status: "verified_l2" } }),
      ev("REVIEWED_L3", "2026-10-24T11:00:00Z", R, { new: { verification_status: "reviewed_l3" } }),
    ]);
    expect(items.map((i) => [i.n, i.label, i.state])).toEqual([
      [1, "Submitted", "submitted"], [2, "Verified by Team Lead", "verified_l2"], [3, "Reviewed by Reviewer", "reviewed_l3"],
    ]);
    expect(items.map((i) => i.current)).toEqual([false, false, true]);
  });

  it("shows an edit that also moved the state as ONE step, with the old and new value", () => {
    const items = buildTimeline([
      ev("CREATED", "2026-10-24T09:00:00.000Z", A, { new: { bottle_count: 11 } }),
      ev("EDITED", "2026-10-24T10:00:00.000Z", L, { old: { bottle_count: 11 }, new: { bottle_count: 14 }, changed_fields: ["bottle_count"], reason: "delivery note says 14" }),
      ev("VERIFIED_L2", "2026-10-24T10:00:00.050Z", L, { new: { verification_status: "verified_l2" } }),
    ]);
    expect(items).toHaveLength(2);
    expect(items[1].label).toBe("Edited and verified by Team Lead");
    expect(items[1].state).toBe("verified_l2");
    expect(items[1].changes).toEqual([{ field: "bottle_count", label: "Bottles (final)", old: "11", neu: "14" }]);
    expect(items[1].reason).toBe("delivery note says 14");
  });

  it("does not merge a verification by someone else, or one that came much later", () => {
    const items = buildTimeline([
      ev("EDITED", "2026-10-24T10:00:00Z", R, { old: { bottle_count: 1 }, new: { bottle_count: 2 }, changed_fields: ["bottle_count"] }),
      ev("VERIFIED_L2", "2026-10-24T10:00:01Z", L, {}),
      ev("EDITED", "2026-10-24T12:00:00Z", L, { old: { bottle_count: 2 }, new: { bottle_count: 3 }, changed_fields: ["bottle_count"] }),
      ev("VERIFIED_L2", "2026-10-24T13:00:00Z", L, {}),
    ]);
    expect(items.map((i) => i.label)).toEqual(["Edited", "Verified by Team Lead", "Edited", "Verified by Team Lead"]);
  });

  it("keeps comments out of the timeline and puts them, with the system's own sentences, in the comments", () => {
    const events = [
      ev("CREATED", "2026-10-24T09:00:00Z", A, { new: { bottle_count: 11 } }),
      ev("CHECK_REQUESTED", "2026-10-24T09:30:00Z", R, { comment: "usually 20" }),
      ev("COMMENTED", "2026-10-24T09:40:00Z", L, { comment: "Calling the store" }),
      ev("REVIEWED_L3", "2026-10-24T11:00:00Z", R, {}),
    ];
    expect(buildTimeline(events).map((i) => i.label)).toEqual(["Submitted", "Verification requested", "Reviewed by Reviewer"]);
    const comments = buildComments(events);
    expect(comments[0].text).toContain("reviewed this entry");                         // newest first
    expect(comments.find((c) => c.mine)?.text).toBe("Calling the store");
    expect(comments.find((c) => c.text.includes("asked the Team Lead"))?.text).toContain('"usually 20"');
    expect(comments.filter((c) => !c.mine).every((c) => c.text.length > 0)).toBe(true);
  });

  it("goes back to Submitted when the number is changed after verification", () => {
    const items = buildTimeline([
      ev("CREATED", "2026-10-24T09:00:00Z", A, {}),
      ev("VERIFIED_L2", "2026-10-24T10:00:00Z", L, {}),
      ev("EDITED", "2026-10-24T11:00:00Z", A, { old: { bottle_count: 11 }, new: { bottle_count: 12 }, changed_fields: ["bottle_count"] }),
      ev("STATUS_CHANGED", "2026-10-24T11:00:00.010Z", A, { old: { verification_status: "verified_l2" }, new: { verification_status: "submitted" } }),
    ]);
    expect(items[items.length - 1].label).toBe("Back to Submitted (the number changed)");
    expect(items[items.length - 1].state).toBe("submitted");
  });
});
