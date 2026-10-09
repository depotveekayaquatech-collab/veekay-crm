import { useMemo, useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { fmtDay } from "@/features/attendance/format";
import { LEAVE_LABEL, LEAVE_TONE, useLeaveMutations, useMyLeaves, type LeaveType } from "@/features/attendance/api";
import { daysAgo } from "@/lib/dates";

const TYPES = (Object.keys(LEAVE_LABEL) as LeaveType[]).map((value) => ({ value, label: LEAVE_LABEL[value] }));

/** Working days between two dates (Sundays are the weekly off and aren't counted). */
function workingDays(start: string, end: string, half: boolean): number {
  if (!start || !end || end < start) return 0;
  let n = 0;
  for (let d = new Date(`${start}T12:00:00`); d <= new Date(`${end}T12:00:00`); d.setDate(d.getDate() + 1)) if (d.getDay() !== 0) n++;
  return half && n === 1 ? 0.5 : n;
}

export function LeavePanel() {
  const year = new Date().getFullYear();
  const { data, isLoading, isError, refetch } = useMyLeaves(year);
  const { apply, cancel } = useLeaveMutations();

  const [type, setType] = useState<LeaveType>("CASUAL");
  const [start, setStart] = useState(daysAgo(0));
  const [end, setEnd] = useState(daysAgo(0));
  const [half, setHalf] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const days = useMemo(() => workingDays(start, end, half), [start, end, half]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apply.mutateAsync({ leave_type: type, start_date: start, end_date: end, half_day: half && start === end, reason: reason.trim() });
      setReason("");
      setHalf(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send the request.");
    }
  }

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[24rem_1fr]">
      <form onSubmit={submit} className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-5 shadow-card">
        <div>
          <h3 className="text-base font-bold text-heading">Apply for leave</h3>
          <p className="text-xs text-gray-500">Your admin approves it; approved leave shows as "On leave", not "Absent".</p>
        </div>
        <Select label="Type of leave" value={type} onChange={(e) => setType(e.target.value as LeaveType)} options={TYPES} />
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="From"
            type="date"
            value={start}
            min={daysAgo(7)}
            onChange={(e) => {
              setStart(e.target.value);
              if (end < e.target.value) setEnd(e.target.value);
            }}
            required
          />
          <Input label="To" type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} required />
        </div>
        {start === end && (
          <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={half} onChange={(e) => setHalf(e.target.checked)} className="accent-brand-500" />
            Half day
          </label>
        )}
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Reason
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            maxLength={500}
            required
            placeholder="A short reason for your admin"
            className="rounded-md border border-surface-border bg-surface px-3 py-2 text-sm font-normal shadow-sm outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </label>
        <p className="rounded-lg bg-surface-subtle px-3 py-2 text-xs text-gray-600">
          {days === 0 ? "Those dates are all weekly offs (Sunday)." : <>This request is for <b>{days}</b> working day{days === 1 ? "" : "s"} (Sundays aren't counted).</>}
        </p>
        {error && <p className="text-sm text-status-danger">{error}</p>}
        <Button type="submit" isLoading={apply.isPending} disabled={!reason.trim() || days === 0}>Send for approval</Button>
      </form>

      <div className="flex min-w-0 flex-col gap-5">
        {data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {TYPES.map((t) => (
              <div key={t.value} className="tile tile-brand rounded-xl border border-surface-border bg-surface p-4 shadow-card">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{t.label}</p>
                <p className="mt-1.5 text-[1.6rem] font-bold leading-none tabular-nums text-heading">{data.taken[t.value] ?? 0}</p>
                <p className="mt-1 text-[11px] text-gray-400">days taken in {year}</p>
              </div>
            ))}
          </div>
        )}

        {isLoading && <Skeleton className="h-48" />}
        {isError && <ErrorState message="Couldn't load your leave." onRetry={() => refetch()} />}
        {data && data.items.length === 0 && <EmptyState title="No leave requests yet" description="Apply on the left — approved leave appears in your attendance." />}

        {data && data.items.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
            <table className="w-full min-w-[620px] text-sm">
              <thead>
                <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                  <th className="px-4 py-3">Dates</th>
                  <th className="px-3 py-3">Type</th>
                  <th className="px-3 py-3 text-right">Days</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-4 py-3 text-right" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((l) => (
                  <tr key={l.id} className="border-t border-surface-border/70 align-top">
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">{l.startDate === l.endDate ? fmtDay(l.startDate) : `${fmtDay(l.startDate)} → ${fmtDay(l.endDate)}`}</div>
                      <div className="max-w-[18rem] truncate text-xs text-gray-500" title={l.reason}>{l.reason}</div>
                    </td>
                    <td className="px-3 py-3 text-gray-700">{LEAVE_LABEL[l.leaveType]}{l.halfDay ? " · half" : ""}</td>
                    <td className="px-3 py-3 text-right font-semibold tabular-nums">{l.days}</td>
                    <td className="px-3 py-3">
                      <Badge tone={LEAVE_TONE[l.status]}>{l.status.charAt(0) + l.status.slice(1).toLowerCase()}</Badge>
                      {l.reviewedByName && <div className="mt-0.5 text-[11px] text-gray-500">by {l.reviewedByName}</div>}
                      {l.reviewNote && <div className="mt-0.5 max-w-[14rem] text-[11px] italic text-gray-500">"{l.reviewNote}"</div>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {l.canCancel && (
                        <button
                          className="text-xs font-semibold text-status-danger hover:underline disabled:opacity-50"
                          disabled={cancel.isPending}
                          onClick={() => confirm("Cancel this leave request?") && cancel.mutate(l.id)}
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
