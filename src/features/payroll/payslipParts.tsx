import { Badge } from "@/components/ui/Badge";
import { SelectField } from "@/components/ui/Dropdown";
import { fmtDay, fmtMinutes, fmtTime } from "@/features/attendance/format";
import type { DayKind, PayDay, PayMark } from "@/features/payroll/api";
import { countedWith, type Pending } from "@/features/payroll/payslipMath";

const KIND: Record<DayKind, { label: string; tone: "success" | "info" | "warning" | "danger" | "neutral" }> = {
  PRESENT: { label: "Present", tone: "success" },
  LEAVE: { label: "On leave", tone: "info" },
  OFF: { label: "Weekly off", tone: "neutral" },
  ABSENT: { label: "Absent", tone: "danger" },
  BEFORE_JOINING: { label: "Before joining", tone: "neutral" },
};

const dayLabel = (n: number) => (n === 1 ? "1 day" : n === 0.5 ? "½ day" : n === 0 ? "0" : `${n} days`);

/** The day-by-day list of a payslip: attendance with time stamps, and (for an admin) the mark to count the day as full / half / unpaid. */
export function DayTable({
  days, pending, onMark, readOnly,
}: {
  days: PayDay[];
  pending?: Pending;
  onMark?: (date: string, mark: PayMark | "AUTO") => void;
  readOnly: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-surface-border">
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <thead>
          <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
            {["Date", "Attendance", "Check in", "Check out", "Hours", "Where", "Counts", readOnly ? "" : "Mark"].map((h, i) => (
              <th key={i} className="border-b border-surface-border px-3 py-2.5">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map((d) => {
            const k = KIND[d.kind];
            const value = countedWith(d, pending);
            const changed = pending?.[d.date] !== undefined && pending[d.date] !== (d.mark ?? "AUTO");
            return (
              <tr key={d.date} className={`border-b border-surface-border/60 ${changed ? "bg-amber-500/5" : ""}`}>
                <td className="whitespace-nowrap px-3 py-2 font-medium text-gray-900">{fmtDay(d.date)}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={k.tone}>{d.kind === "LEAVE" && d.leaveType ? `${d.leaveType.toLowerCase()} leave${d.halfDay ? " (½)" : ""}` : k.label}</Badge>
                    {d.late && <Badge tone="warning">Late</Badge>}
                  </div>
                </td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">{fmtTime(d.checkInAt)}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                  {d.noCheckout ? <span className="text-status-warning">Not checked out</span> : fmtTime(d.checkOutAt)}
                </td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">{d.checkInAt ? fmtMinutes(d.minutes) : "—"}</td>
                <td className="max-w-[160px] truncate px-3 py-2 text-xs text-gray-600" title={d.location ?? undefined}>{d.location ?? "—"}</td>
                <td className={`whitespace-nowrap px-3 py-2 font-semibold tabular-nums ${value === 0 ? "text-gray-400" : "text-gray-900"}`}>{dayLabel(value)}</td>
                {!readOnly && (
                  <td className="px-3 py-2">
                    <SelectField
                      className="h-8 rounded-lg border border-surface-border bg-surface px-2 text-xs"
                      value={pending?.[d.date] ?? d.mark ?? "AUTO"}
                      onChange={(e) => onMark?.(d.date, e.target.value as PayMark | "AUTO")}
                      aria-label={`Mark for ${fmtDay(d.date)}`}
                    >
                      <option value="AUTO">Auto</option>
                      <option value="FULL">Full day</option>
                      <option value="HALF">Half day</option>
                      <option value="ABSENT">Unpaid</option>
                    </SelectField>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
