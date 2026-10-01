import { Fragment, useState } from "react";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { LocationBadge, StatusBadge } from "@/features/attendance/parts";
import { fmtDay, fmtMinutes, fmtTime } from "@/features/attendance/format";
import { useMyAttendance } from "@/features/attendance/api";

const field = "h-10 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

function thisMonth(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`;
}

/** Your own sign-in / sign-out times for a month. */
export function MyAttendance() {
  const [month, setMonth] = useState(thisMonth());
  const [open, setOpen] = useState<string | null>(null);
  const { data, isLoading, isError, refetch } = useMyAttendance(month);

  const me = data?.rows[0];
  const days = me ? Object.entries(me.days).sort(([a], [b]) => (a < b ? 1 : -1)) : [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
          Month
          <input type="month" className={field} value={month} max={thisMonth()} onChange={(e) => e.target.value && setMonth(e.target.value)} />
        </label>
      </div>

      {me && (
        <div className="grid grid-cols-3 gap-3">
          {[
            ["Days present", me.daysPresent, "brand"],
            ["Hours signed in", (me.totalMinutes / 60).toFixed(1), "aqua"],
            ["Avg per day", me.daysPresent ? `${(me.totalMinutes / 60 / me.daysPresent).toFixed(1)} h` : "—", "success"],
          ].map(([t, v, tone]) => (
            <div key={t as string} className={`tile tile-${tone} rounded-xl border border-surface-border bg-white p-4 shadow-card`}>
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{t}</p>
              <p className="mt-1.5 text-[1.6rem] font-bold leading-none tabular-nums text-ink-900">{v}</p>
            </div>
          ))}
        </div>
      )}

      {isLoading && <Skeleton className="h-56" />}
      {isError && <ErrorState message="Couldn't load your attendance." onRetry={() => refetch()} />}
      {data && days.length === 0 && <EmptyState title="No sign-ins this month" description="Your sign-in and sign-out times will appear here." />}

      {days.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-surface-border bg-white shadow-card">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3">Date</th>
                <th className="px-3 py-3">Login</th>
                <th className="px-3 py-3">Logout</th>
                <th className="px-3 py-3 text-right">Hours</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3">Location</th>
                <th className="px-4 py-3 text-right">Sign-ins</th>
              </tr>
            </thead>
            <tbody>
              {days.map(([d, e]) => (
                <Fragment key={d}>
                  <tr className="border-t border-surface-border/70 align-top">
                    <td className="px-4 py-3 font-medium text-gray-900">{fmtDay(d)}</td>
                    <td className="px-3 py-3 tabular-nums">{fmtTime(e.firstLogin)}</td>
                    <td className="px-3 py-3 tabular-nums">{e.lastLogout ? fmtTime(e.lastLogout) : <span className="text-xs text-gray-400">{e.status === "ACTIVE" ? "still signed in" : "didn't sign out"}</span>}</td>
                    <td className="px-3 py-3 text-right font-semibold tabular-nums text-ink-900">{fmtMinutes(e.minutes)}</td>
                    <td className="px-3 py-3"><StatusBadge status={e.status} /></td>
                    <td className="px-3 py-3"><LocationBadge location={e.location} /></td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => setOpen(open === d ? null : d)} className="text-xs font-semibold text-brand-600 hover:text-brand-700">
                        {e.signIns} {open === d ? "▲" : "▼"}
                      </button>
                    </td>
                  </tr>
                  {open === d && (
                    <tr className="bg-surface-subtle/60">
                      <td colSpan={7} className="px-4 py-3">
                        <ul className="flex flex-col gap-2 text-xs">
                          {(e.sessions ?? []).map((se) => (
                            <li key={se.id} className="flex flex-wrap items-start gap-x-4 gap-y-1">
                              <span className="font-medium tabular-nums">{fmtTime(se.loginAt)} → {se.logoutAt ? fmtTime(se.logoutAt) : "…"}</span>
                              <span className="tabular-nums text-gray-500">{fmtMinutes(se.minutes)}</span>
                              <Badge tone={se.state === "active" ? "success" : se.state === "idle" ? "warning" : "neutral"}>{se.state.replace("_", " ")}</Badge>
                              <LocationBadge location={se.location} />
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
