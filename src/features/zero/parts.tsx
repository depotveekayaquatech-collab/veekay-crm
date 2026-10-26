import { Badge } from "@/components/ui/Badge";
import type { ReviewState, Severity, Streak } from "@/features/zero/api";

export const fmtDay = (iso: string | null | undefined) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—");
export const fmtShort = (iso: string | null | undefined) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "—");
export const fmtMoment = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true }) + " IST" : "—";
export const monthLabel = (ym: string) => new Date(`${ym}-01T12:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });

/** How loud a row should be, from how long its streak is. */
export const ROW_TONE: Record<Severity, string> = {
  none: "",
  low: "bg-amber-500/5",
  medium: "bg-amber-500/10",
  high: "bg-orange-500/15",
  critical: "bg-rose-500/15",
};
export const SEVERITY_BADGE: Record<Severity, "neutral" | "warning" | "danger"> = { none: "neutral", low: "neutral", medium: "warning", high: "danger", critical: "danger" };

const STATE: Record<ReviewState, { label: string; tone: "warning" | "info" | "success" | "danger" }> = {
  pending: { label: "Pending", tone: "warning" }, reviewed: { label: "Reviewed", tone: "info" }, verified: { label: "Verified", tone: "success" }, flagged: { label: "Flagged", tone: "danger" },
};
export const StateBadge = ({ state }: { state: ReviewState }) => <Badge tone={STATE[state].tone} dot>{STATE[state].label}</Badge>;

export function StreakCell({ streak, severity }: { streak: Streak | null; severity: Severity }) {
  if (!streak) return <span className="text-gray-400">none</span>;
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <Badge tone={SEVERITY_BADGE[severity]}>{streak.length} day{streak.length === 1 ? "" : "s"}</Badge>
        {streak.ongoing && <span className="text-[11px] font-bold uppercase tracking-wide text-status-danger">ongoing</span>}
      </div>
      <p className="mt-0.5 text-xs text-gray-500">{fmtShort(streak.start)} → {fmtShort(streak.end)}</p>
    </div>
  );
}

export function Employees({ people }: { people: { name: string }[] }) {
  if (people.length === 0) return <span className="text-gray-400">unassigned</span>;
  return <span>{people.map((p) => p.name).join(", ")}</span>;
}
