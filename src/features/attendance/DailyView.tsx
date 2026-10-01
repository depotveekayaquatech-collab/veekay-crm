import { Fragment, useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconDownload, IconSearch } from "@/components/ui/icons";
import { CategoryChips, GroupRow, LocationBadge, StatusBadge } from "@/features/attendance/parts";
import { fmtMinutes, fmtTime } from "@/features/attendance/format";
import { useDayAttendance, type DayStatus } from "@/features/attendance/api";
import { downloadCsv } from "@/lib/csv";
import { daysAgo } from "@/lib/dates";

const field = "h-10 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

function Tile({ title, value, tone, hint }: { title: string; value: number | string; tone: "brand" | "aqua" | "success" | "warning"; hint?: string }) {
  return (
    <div className={`tile tile-${tone} rounded-xl border border-surface-border bg-white p-4 shadow-card`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{title}</p>
      <p className="mt-1.5 text-[1.6rem] font-bold leading-none tabular-nums text-ink-900">{value}</p>
      {hint && <p className="mt-1 text-[11px] text-gray-400">{hint}</p>}
    </div>
  );
}

export function DailyView() {
  const [date, setDate] = useState(daysAgo(0));
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | DayStatus>("");
  const [cat, setCat] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
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
      ["Date", "Employee ID", "Name", "Role", "Platform", "Status", "First login", "Last logout", "Last active", "Hours", "Sign-ins", "Location", "Latitude", "Longitude", "Distance to office (m)"],
      rows.map((r) => [
        data.date, r.employeeCode, r.fullName, r.roles.join("/"), r.platform, r.status,
        fmtTime(r.firstLogin), fmtTime(r.lastLogout), fmtTime(r.lastActive), (r.minutes / 60).toFixed(2), r.signIns,
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
              className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${date === daysAgo(n as number) ? "bg-brand-500 text-white" : "bg-white text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"}`}
            >
              {l}
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
          Status
          <select className={field} value={status} onChange={(e) => setStatus(e.target.value as "" | DayStatus)}>
            <option value="">All</option>
            <option value="ACTIVE">Active now</option>
            <option value="SIGNED_OUT">Signed out</option>
            <option value="IDLE">Idle</option>
            <option value="ABSENT">Absent</option>
          </select>
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

      {s && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Tile title="Expected" value={s.expected} tone="brand" hint="employees + accountants" />
          <Tile title="Present" value={s.present} tone="success" />
          <Tile title="Active now" value={s.activeNow} tone="aqua" />
          <Tile title="Absent" value={s.absent} tone="warning" />
          <Tile title="Outside office" value={s.outsideOffice} tone="warning" hint="signed in elsewhere" />
          <Tile title="Location not shared" value={s.locationUnknown} tone="brand" />
        </div>
      )}

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load attendance." onRetry={() => refetch()} />}

      {data && (
        <div className="overflow-x-auto rounded-xl border border-surface-border bg-white shadow-card">
          <table className="w-full min-w-[980px] text-sm">
            <thead>
              <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3">Employee</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3">Login time</th>
                <th className="px-3 py-3">Logout time</th>
                <th className="px-3 py-3">Last active</th>
                <th className="px-3 py-3 text-right">Hours</th>
                <th className="px-3 py-3">Sign-in location</th>
                <th className="w-16 px-4 py-3 text-right">Sign-ins</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-gray-500">No one matches.</td>
                </tr>
              )}
              {rows.map((r, i) => {
                const expanded = open.has(r.userId);
                const newGroup = i === 0 || rows[i - 1].category !== r.category;
                return (
                  <Fragment key={r.userId}>
                    {newGroup && <GroupRow colSpan={8} label={r.categoryLabel} count={rows.filter((x) => x.category === r.category).length} />}
                    <tr className={`border-t border-surface-border/70 align-top ${r.status === "ABSENT" ? "bg-status-danger-soft/20" : ""}`}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900">{r.fullName}</div>
                        <div className="text-[11px] text-gray-500">
                          {r.employeeCode}
                          {r.platform ? ` · ${r.platform}` : ""}
                          {r.region ? ` · ${r.region}` : ""}
                        </div>
                      </td>
                      <td className="px-3 py-3"><StatusBadge status={r.status} /></td>
                      <td className="px-3 py-3 font-medium tabular-nums text-gray-900">{fmtTime(r.firstLogin)}</td>
                      <td className="px-3 py-3 tabular-nums">
                        {r.lastLogout ? <span className="font-medium text-gray-900">{fmtTime(r.lastLogout)}</span> : r.status === "ABSENT" ? "—" : <span className="text-xs text-gray-400">{r.status === "ACTIVE" ? "still signed in" : "didn't sign out"}</span>}
                      </td>
                      <td className="px-3 py-3 tabular-nums text-gray-600">{fmtTime(r.lastActive)}</td>
                      <td className="px-3 py-3 text-right font-semibold tabular-nums text-ink-900">{r.status === "ABSENT" ? "—" : fmtMinutes(r.minutes)}</td>
                      <td className="px-3 py-3"><LocationBadge location={r.location} /></td>
                      <td className="px-4 py-3 text-right">
                        {r.signIns > 0 ? (
                          <button
                            onClick={() => setOpen((p) => { const n = new Set(p); if (n.has(r.userId)) n.delete(r.userId); else n.add(r.userId); return n; })}
                            className="text-xs font-semibold text-brand-600 hover:text-brand-700"
                            aria-expanded={expanded}
                          >
                            {r.signIns} {expanded ? "▲" : "▼"}
                          </button>
                        ) : (
                          <span className="text-gray-300">0</span>
                        )}
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="bg-surface-subtle/60">
                        <td colSpan={8} className="px-4 py-3">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left font-bold uppercase tracking-wider text-gray-500">
                                <th className="py-1 pr-3">Signed in</th>
                                <th className="py-1 pr-3">Signed out</th>
                                <th className="py-1 pr-3">State</th>
                                <th className="py-1 pr-3">Duration</th>
                                <th className="py-1 pr-3">IP</th>
                                <th className="py-1">Location</th>
                              </tr>
                            </thead>
                            <tbody>
                              {r.sessions.map((se) => (
                                <tr key={se.id} className="border-t border-surface-border/60 align-top">
                                  <td className="py-1.5 pr-3 font-medium tabular-nums">{fmtTime(se.loginAt)}</td>
                                  <td className="py-1.5 pr-3 tabular-nums">{se.logoutAt ? `${fmtTime(se.logoutAt)}${se.endedBy === "revoked" ? " (ended)" : ""}` : "—"}</td>
                                  <td className="py-1.5 pr-3">
                                    <Badge tone={se.state === "active" ? "success" : se.state === "idle" ? "warning" : "neutral"}>{se.state.replace("_", " ")}</Badge>
                                  </td>
                                  <td className="py-1.5 pr-3 tabular-nums">{fmtMinutes(se.minutes)}</td>
                                  <td className="py-1.5 pr-3 text-gray-500">{se.ip ?? "—"}</td>
                                  <td className="py-1.5"><LocationBadge location={se.location} /></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {isFetching && !isLoading && <p className="-mt-3 text-xs text-gray-400">Refreshing…</p>}
      <p className="text-xs text-gray-400">
        Login time is the first sign-in of the day, logout time the last time they signed out. If someone closes the tab without signing out,
        their time counts until they were last active. Locations come from the device and can be faked.
      </p>
    </div>
  );
}
