import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { priorityLines } from "@/features/cappingPlanner/helpers";
import type { PriorityEntry, PriorityStatus } from "@/services/cappingPlanner";

const PLACEHOLDER = "Paste priority store names or Outlet IDs here, one per line...\n\nDEL-ROHINI Sector 15\nDEL-SHAKTI NAGAR\nGZB-GAUR CITY\nDEL-Connaught Place";
const PAGE = 100;
const STATUS: Record<PriorityStatus, { label: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  matched: { label: "Matched", tone: "success" },
  duplicate: { label: "Duplicate", tone: "warning" },
  ambiguous: { label: "Ambiguous", tone: "warning" },
  other_project: { label: "Other project", tone: "warning" },
  unmatched: { label: "Not found", tone: "danger" },
};

/** The textarea for the priority list (kept exactly as pasted, first line = highest priority) and, after a calculation, how every line was read. */
export function PriorityPanel({ text, onText, entries, stale, onRemove }: { text: string; onText: (t: string) => void; entries: PriorityEntry[] | null; stale: boolean; onRemove: (position: number) => void }) {
  const [shown, setShown] = useState(PAGE);
  const lines = priorityLines(text).length;
  const counts = entries ? Object.fromEntries((Object.keys(STATUS) as PriorityStatus[]).map((s) => [s, entries.filter((e) => e.status === s).length])) : null;
  const unresolved = counts ? counts.unmatched + counts.ambiguous + counts.other_project + counts.duplicate : 0;

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface p-4 shadow-card" aria-label="Priority stores">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-bold text-gray-900">Priority stores</h2>
          <p className="text-xs text-gray-500">One store per line, by name, Outlet ID or system code. The first line has the highest priority. Nothing is pre-filled.</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => { onText(""); setShown(PAGE); }} disabled={!text}>Clear list</Button>
      </div>
      <textarea
        value={text}
        onChange={(e) => onText(e.target.value)}
        placeholder={PLACEHOLDER}
        rows={7}
        spellCheck={false}
        aria-label="Priority stores, one per line"
        className="w-full resize-y rounded-lg border border-surface-border bg-surface p-3 font-mono text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
      />
      <p className="text-xs text-gray-500">{lines.toLocaleString("en-IN")} line{lines === 1 ? "" : "s"} pasted{stale && entries ? " · the list changed since the last calculation, press Calculate to match it again" : ""}</p>

      {entries && counts && entries.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge tone="success">{counts.matched} matched</Badge>
            {unresolved > 0 && <Badge tone="danger">{unresolved} need attention</Badge>}
          </div>
          {unresolved > 0 && <p className="text-xs text-gray-600">Entries that are not matched are left out of the plan until you fix the line or remove it. Nothing is dropped silently.</p>}
          <ul className="divide-y divide-surface-border/70 rounded-lg border border-surface-border">
            {entries.slice(0, shown).map((e) => (
              <li key={`${e.position}-${e.raw}`} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2 text-sm">
                <span className="w-8 shrink-0 tabular-nums text-xs font-bold text-gray-400">#{e.position}</span>
                <div className="min-w-0 flex-1">
                  <p className="break-words font-semibold text-gray-900">{e.name ?? e.raw}</p>
                  <p className="break-all text-xs text-gray-500">{e.name && e.name !== e.raw ? `pasted “${e.raw}” · ` : ""}{e.crmCode ?? ""}{e.outletId ? ` · ${e.outletId}` : ""}</p>
                  <p className={`text-xs ${e.included ? "text-status-success" : "text-gray-600"}`}>{e.status === "matched" || e.status === "duplicate" ? e.outcome : e.message}</p>
                  {e.status === "ambiguous" && (
                    <ul className="mt-1 text-xs text-gray-600">
                      {e.candidates.map((c) => <li key={c.crmCode} className="break-all">{c.crmCode} · {c.outletId} · {c.name} · {c.project}</li>)}
                    </ul>
                  )}
                </div>
                <Badge tone={STATUS[e.status].tone}>{STATUS[e.status].label}</Badge>
                <button type="button" onClick={() => onRemove(e.position)} aria-label={`Remove ${e.raw} from the priority list`} className="rounded px-2 text-lg leading-none text-gray-400 hover:text-status-danger">×</button>
              </li>
            ))}
          </ul>
          {entries.length > shown && <Button variant="secondary" size="sm" onClick={() => setShown((v) => v + PAGE)}>Show more ({entries.length - shown} left)</Button>}
        </div>
      )}
    </section>
  );
}
