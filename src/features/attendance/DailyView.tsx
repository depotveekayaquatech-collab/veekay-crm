import { Fragment, useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconDownload } from "@/components/ui/icons";
import { Select } from "@/components/ui/Select";
import { SearchBox } from "@/features/orders/ui";
import { CategoryChips, GroupRow, LocationBadge, StatusBadge } from "@/features/attendance/parts";
import { fmtMinutes, fmtTime } from "@/features/attendance/format";
import { LEAVE_LABEL, useDayAttendance, type DayStatus } from "@/features/attendance/api";
import { downloadCsv } from "@/lib/csv";
import { daysAgo } from "@/lib/dates";

const field = "h-10 rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

function Tile({ title, value, tone, hint }: { title: string; value: number | string; tone: "brand" | "aqua" | "success" | "warning"; hint?: string }) {
  return (
    <div className={`tile tile-${tone} rounded-xl border border-surface-border bg-surface p-4 shadow-card`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{title}</p>
      <p className="mt-1.5 text-[1.6rem] font-bold leading-none tabular-nums text-heading">{value}</p>
      {hint && <p className="mt-1 text-[11px] text-gray-400">{hint}</p>}
    </div>
  );
}

const STATUS_OPTIONS = [
  { value: "CHECKED_IN", label: "Checked in" },
  { value: "CHECKED_OUT", label: "Checked out" },
  { value: "NO_CHECKOUT", label: "No check-out" },
  { value: "ON_LEAVE", label: "On leave" },
  { value: "ABSENT", label: "Absent" },
];

export function DailyView() {
  const [date, setDate] = useState(daysAgo(0));
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | DayStatus>("");
  const [cat, setCat] = useState("");
  const { data, isLoading, isError, refetch, isFetching } = useDayAttendance(date);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.rows ?? []).filter(
      (r) =>
        (!status || r.status === status) &&
        (!cat || r.category === cat) &&
        (!needle || [r.fullName, r.employeeCode, r.platform, r.region].some((f) => (f ?? "").toLowerCase().includes(needle))),
    );
  }, [data, q, status, cat]);

  function exportCsv() {
    if (!data) return;
    downloadCsv(
      `attendance-${data.date}.csv`,
      ["Date", "Employee ID", "Name", "Role", "Platform", "Status", "Late", "Check in", "Check out", "Hours", "Check-in location", "Latitude", "Longitude", "Distance to office (m)"],
      rows.map((r) => [
        data.date, r.employeeCode, r.fullName, r.roles.join("/"), r.platform, r.status, r.late ? "Yes" : "",
        fmtTime(r.checkInAt), fmtTime(r.checkOutAt), (r.minutes / 60).toFixed(2),
        r.location.status === "office" ? r.location.label : r.location.status === "outside" ? "Outside office" : "Not shared",
        r.location.latitude, r.location.longitude, r.location.distanceM,
      ]),
    );
  }

  const s = data?.summary;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
          Date
          <input type="date" className={field} value={date} max={daysAgo(0)} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
        <div className="flex gap-1 pb-0.5">
          {[["Today", 0], ["Yesterday", 1]].map(([l, n]) => (
            <button
              key={l as string}
              onClick={() => setDate(daysAgo(n as number))}
              className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${date === daysAgo(n as number) ? "bg-brand-500 text-white" : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"}`}
            >
              {l}
            </button>
          ))}
        </div>
        <div className="w-full sm:w-44">
          <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value as "" | DayStatus)} placeholder="All" options={STATUS_OPTIONS} />
        </div>
        <SearchBox value={q} onChange={setQ} placeholder="Search name, ID, platform…" className="w-full sm:ml-auto sm:w-72" />
        <Button variant="secondary" onClick={exportCsv} disabled={!rows.length}>
          <IconDownload className="h-4 w-4" />
          Export CSV
        </Button>
      </div>

      {data && <CategoryChips rows={data.rows} value={cat} onChange={setCat} />}

      {data?.isWeeklyOff && (
        <p className="rounded-lg bg-surface-subtle px-4 py-3 text-sm text-gray-600">This day is the weekly off — nobody is expected, so no one is marked absent.</p>
      )}

      {s && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
          <Tile title="Expected" value={s.expected} tone="brand" hint="employees + accounts" />
          <Tile title="Present" value={s.present} tone="success" />
          <Tile title="Still in" value={s.checkedInNow} tone="aqua" hint="not checked out yet" />
          <Tile title="Late" value={s.late} tone="warning" />
          <Tile title="On leave" value={s.onLeave} tone="brand" />
          <Tile title="Absent" value={s.absent} tone="warning" />
          <Tile title="Outside office" value={s.outsideOffice} tone="warning" hint="checked in elsewhere" />
        </div>
      )}

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load attendance." onRetry={() => refetch()} />}

      {data && (
        <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
          <table className="w-full min-w-[920px] text-sm">
            <thead>
              <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3">Employee</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3">Check in</th>
                <th className="px-3 py-3">Check out</th>
                <th className="px-3 py-3 text-right">Hours</th>
                <th className="px-4 py-3">Check-in location</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-gray-500">No one matches.</td>
                </tr>
              )}
              {rows.map((r, i) => {
                const newGroup = i === 0 || rows[i - 1].category !== r.category;
                const present = r.status === "CHECKED_IN" || r.status === "CHECKED_OUT" || r.status === "NO_CHECKOUT";
                return (
                  <Fragment key={r.userId}>
                    {newGroup && <GroupRow colSpan={6} label={r.categoryLabel} count={rows.filter((x) => x.category === r.category).length} />}
                    <tr className={`border-t border-surface-border/70 align-top ${r.status === "ABSENT" ? "bg-status-danger-soft/20" : ""}`}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900">{r.fullName}</div>
                        <div className="text-[11px] text-gray-500">
                          {r.employeeCode}
                          {r.platform ? ` · ${r.platform}` : ""}
                          {r.region ? ` · ${r.region}` : ""}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StatusBadge status={r.status} />
                          {r.late && <Badge tone="warning">Late</Badge>}
                        </div>
                        {r.status === "ON_LEAVE" && r.leaveType && <div className="mt-0.5 text-[11px] text-gray-500">{LEAVE_LABEL[r.leaveType]}</div>}
                      </td>
                      <td className="px-3 py-3 font-medium tabular-nums text-gray-900">{fmtTime(r.checkInAt)}</td>
                      <td className="px-3 py-3 tabular-nums">
                        {r.checkOutAt ? (
                          <div>
                            <span className="font-medium text-gray-900">{fmtTime(r.checkOutAt)}</span>
                            {r.checkOutLocation?.status === "outside" && <div className="text-[11px] text-status-warning">outside office</div>}
                          </div>
                        ) : present ? (
                          <span className="text-xs text-gray-400">{r.status === "CHECKED_IN" ? "still in" : "didn't check out"}</span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-3 py-3 text-right font-semibold tabular-nums text-heading">{present ? fmtMinutes(r.minutes) : "—"}</td>
                      <td className="px-4 py-3">{present ? <LocationBadge location={r.location} /> : <span className="text-gray-300">—</span>}</td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {isFetching && !isLoading && <p className="-mt-3 text-xs text-gray-400">Refreshing…</p>}
      <p className="text-xs text-gray-400">
        Late means checking in after the work start time plus the grace period. Sundays are the weekly off. Locations come from the device and can be faked.
      </p>
    </div>
  );
}
