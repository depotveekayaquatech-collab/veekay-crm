import { Fragment, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconDownload, IconSearch } from "@/components/ui/icons";
import { fmtMinutes, fmtTime } from "@/features/attendance/format";
import { CategoryChips, GroupRow } from "@/features/attendance/parts";
import { useMonthAttendance } from "@/features/attendance/api";
import { downloadCsv } from "@/lib/csv";

const field = "h-10 rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

function thisMonth(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`;
}

export function MonthlyView() {
  const [month, setMonth] = useState(thisMonth());
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const { data, isLoading, isError, refetch } = useMonthAttendance(month);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.rows ?? []).filter(
      (r) => (!cat || r.category === cat) && (!needle || [r.fullName, r.employeeCode, r.platform].some((f) => (f ?? "").toLowerCase().includes(needle))),
    );
  }, [data, q, cat]);

  function exportCsv() {
    if (!data) return;
    downloadCsv(
      `attendance-${data.month}.csv`,
      ["Employee ID", "Name", "Platform", "Days present", "Hours", "Late", "Leave", "Absent", "Days outside office", ...data.dates.map((d) => d.slice(8))],
      rows.map((r) => [
        r.employeeCode, r.fullName, r.platform, r.daysPresent, (r.totalMinutes / 60).toFixed(1), r.lateDays, r.leaveDays, r.absentDays, r.outsideDays,
        ...data.dates.map((d) => (r.days[d] ? (r.days[d].status === "ON_LEAVE" ? "L" : (r.days[d].minutes / 60).toFixed(1)) : "")),
      ]),
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
          Month
          <input type="month" className={field} value={month} max={thisMonth()} onChange={(e) => e.target.value && setMonth(e.target.value)} />
        </label>
        <div className="relative ml-auto w-full sm:w-72">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input className={`${field} w-full pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, ID, platform…" aria-label="Search" />
        </div>
        <Button variant="secondary" onClick={exportCsv} disabled={!rows.length}>
          <IconDownload className="h-4 w-4" />
          Export CSV
        </Button>
      </div>

      {data && <CategoryChips rows={data.rows} value={cat} onChange={setCat} />}

      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-500">
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded bg-status-success-soft ring-1 ring-status-success/30" /> checked in at the office</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded bg-status-warning-soft ring-1 ring-status-warning/30" /> checked in from elsewhere</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded bg-surface-muted ring-1 ring-gray-300" /> location not shared</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded bg-status-info-soft ring-1 ring-status-info/30" /> L = on leave</span>
        <span>Numbers are hours worked · underlined = late · hover a day for the times</span>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load attendance." onRetry={() => refetch()} />}

      {data && (
        <div className="max-h-[70vh] overflow-auto rounded-xl border border-surface-border bg-surface shadow-card">
          <table className="min-w-full border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 top-0 z-30 min-w-[13rem] border-b border-r border-surface-border bg-ink-800 px-3 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-white/70">Employee</th>
                {data.dates.map((d) => {
                  const dt = new Date(`${d}T12:00:00`);
                  const sunday = dt.getDay() === 0;
                  return (
                    <th key={d} className={`sticky top-0 z-20 min-w-[2.4rem] border-b border-surface-border px-1 py-1.5 text-center ${sunday ? "bg-ink-700" : "bg-ink-800"}`}>
                      <div className="text-[11px] font-bold text-white">{d.slice(8)}</div>
                      <div className="text-[9px] font-medium uppercase text-white/50">{dt.toLocaleDateString(undefined, { weekday: "short" }).slice(0, 2)}</div>
                    </th>
                  );
                })}
                <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-700 px-3 py-2.5 text-center text-[11px] font-bold uppercase tracking-wider text-white">Days</th>
                <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-700 px-3 py-2.5 text-center text-[11px] font-bold uppercase tracking-wider text-white">Hours</th>
                <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-700 px-3 py-2.5 text-center text-[11px] font-bold uppercase tracking-wider text-white" title="Days late">Late</th>
                <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-700 px-3 py-2.5 text-center text-[11px] font-bold uppercase tracking-wider text-white" title="Leave days">Leave</th>
                <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-700 px-3 py-2.5 text-center text-[11px] font-bold uppercase tracking-wider text-white" title="Working days with no check-in and no leave">Absent</th>
                <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-700 px-3 py-2.5 text-center text-[11px] font-bold uppercase tracking-wider text-white" title="Days checked in from outside the office">Away</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={data.dates.length + 7} className="px-4 py-10 text-center text-gray-500">No one matches.</td></tr>
              )}
              {rows.map((r, i) => (
                <Fragment key={r.userId}>
                {(i === 0 || rows[i - 1].category !== r.category) && <GroupRow colSpan={data.dates.length + 7} label={r.categoryLabel} count={rows.filter((x) => x.category === r.category).length} />}
                <tr className="group">
                  <td className="sticky left-0 z-10 border-b border-r border-surface-border/70 bg-surface px-3 py-2 group-hover:bg-surface-subtle">
                    <div className="max-w-[12rem] truncate font-medium text-gray-900" title={r.fullName}>{r.fullName}</div>
                    <div className="text-[11px] text-gray-500">{r.employeeCode}{r.platform ? ` · ${r.platform}` : ""}</div>
                  </td>
                  {data.dates.map((d) => {
                    const e = r.days[d];
                    const sunday = new Date(`${d}T12:00:00`).getDay() === 0;
                    if (!e) return <td key={d} className={`border-b border-surface-border/60 px-1 py-2 text-center text-gray-200 ${sunday ? "bg-surface-subtle" : ""}`}>{d > data.today ? "" : "·"}</td>;
                    if (e.status === "ON_LEAVE") {
                      return (
                        <td key={d} className="border-b border-surface-border/60 px-0.5 py-1.5 text-center" title={`On leave${e.halfDay ? " (half day)" : ""}`}>
                          <span className="inline-block min-w-[1.9rem] rounded bg-status-info-soft px-1 py-0.5 text-[11px] font-bold text-status-info">L</span>
                        </td>
                      );
                    }
                    const tone = e.location.status === "office" ? "bg-status-success-soft text-status-success" : e.location.status === "outside" ? "bg-status-warning-soft text-status-warning" : "bg-surface-muted text-gray-600";
                    const tip = `${fmtTime(e.checkInAt)}${e.late ? " (late)" : ""} → ${e.checkOutAt ? fmtTime(e.checkOutAt) : "no check-out"} · ${fmtMinutes(e.minutes)} · ${e.location.status === "office" ? e.location.label : e.location.status === "outside" ? `outside office (${e.location.label})` : "location not shared"}`;
                    return (
                      <td key={d} className="border-b border-surface-border/60 px-0.5 py-1.5 text-center" title={tip}>
                        <span className={`inline-block min-w-[1.9rem] rounded px-1 py-0.5 text-[11px] font-bold tabular-nums ${tone} ${e.late ? "underline decoration-status-warning decoration-2 underline-offset-2" : ""}`}>{(e.minutes / 60).toFixed(1)}</span>
                      </td>
                    );
                  })}
                  <td className="border-b border-surface-border/70 bg-surface-subtle px-3 py-2 text-center font-bold tabular-nums text-heading">{r.daysPresent}</td>
                  <td className="border-b border-surface-border/70 bg-surface-subtle px-3 py-2 text-center font-bold tabular-nums text-heading">{(r.totalMinutes / 60).toFixed(1)}</td>
                  <td className={`border-b border-surface-border/70 bg-surface-subtle px-3 py-2 text-center font-bold tabular-nums ${r.lateDays ? "text-status-warning" : "text-gray-300"}`}>{r.lateDays}</td>
                  <td className={`border-b border-surface-border/70 bg-surface-subtle px-3 py-2 text-center font-bold tabular-nums ${r.leaveDays ? "text-status-info" : "text-gray-300"}`}>{r.leaveDays}</td>
                  <td className={`border-b border-surface-border/70 bg-surface-subtle px-3 py-2 text-center font-bold tabular-nums ${r.absentDays ? "text-status-danger" : "text-gray-300"}`}>{r.absentDays}</td>
                  <td className={`border-b border-surface-border/70 bg-surface-subtle px-3 py-2 text-center font-bold tabular-nums ${r.outsideDays ? "text-status-warning" : "text-gray-300"}`}>{r.outsideDays}</td>
                </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
