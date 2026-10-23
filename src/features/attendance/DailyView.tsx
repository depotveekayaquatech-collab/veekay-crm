import { Fragment, useMemo, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { usePermission } from "@/hooks/usePermission";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconDownload } from "@/components/ui/icons";
import { Select } from "@/components/ui/Select";
import { SearchBox } from "@/features/orders/ui";
import { CategoryChips, GroupRow, LocationBadge, StatusBadge } from "@/features/attendance/parts";
import { fmtMinutes, fmtTime } from "@/features/attendance/format";
import { LEAVE_LABEL, useCorrectRecord, useDayAttendance, type DayRow, type DayStatus, type RecordCorrection } from "@/features/attendance/api";
import { downloadCsv } from "@/lib/csv";
import { locationText, presenceText } from "@/features/attendance/format";
import { daysAgo } from "@/lib/dates";

function Tile({ title, value, tone, hint }: { title: string; value: number | string; tone: "brand" | "aqua" | "success" | "warning"; hint?: string }) {
  const topGradients = {
    brand: "from-brand-500 to-brand-600",
    aqua: "from-aqua-400 to-brand-500",
    success: "from-emerald-400 to-teal-500",
    warning: "from-amber-400 to-orange-500",
  };
  return (
    <div className={`relative overflow-hidden tile tile-${tone} rounded-2xl border border-surface-border bg-surface p-4 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover`}>
      <span aria-hidden="true" className={`pointer-events-none absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r ${topGradients[tone]}`} />
      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{title}</p>
      <p className="mt-1.5 text-[1.65rem] font-extrabold leading-none tabular-nums text-heading tracking-tight">{value}</p>
      {hint && <p className="mt-1 text-[11px] font-medium text-gray-400 truncate">{hint}</p>}
    </div>
  );
}

const STATUS_OPTIONS = [
  { value: "CHECKED_IN", label: "Checked in" },
  { value: "CHECKED_OUT", label: "Checked out" },
  { value: "NO_CHECKOUT", label: "No check-out" },
  { value: "PRESENT", label: "Present (sheet)" },
  { value: "ON_LEAVE", label: "On leave" },
  { value: "ABSENT", label: "Absent" },
];

function hhmm(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Developer-only fix for one person's day: when they checked in, and whether that counts as at the office or away. */
function EditRecordModal({ row, date, onClose }: { row: DayRow | null; date: string; onClose: () => void }) {
  return row ? <EditRecordForm key={row.userId} row={row} date={date} onClose={onClose} /> : null;
}

function EditRecordForm({ row, date, onClose }: { row: DayRow; date: string; onClose: () => void }) {
  const correct = useCorrectRecord();
  const [time, setTime] = useState(hhmm(row.checkInAt));
  const [presence, setPresence] = useState(row.location.status === "office" ? "office" : "away");
  const [late, setLate] = useState(row.late ? "yes" : "no");
  const [half, setHalf] = useState(row.halfDay ? "yes" : "no");
  const [checkOut, setCheckOut] = useState("keep");

  const body: RecordCorrection = { user_id: row.userId, work_date: date };
  if (time && time !== hhmm(row.checkInAt)) body.check_in_time = time;
  if (presence !== (row.location.status === "office" ? "office" : "away")) body.presence = presence as "office" | "away";
  if ((late === "yes") !== row.late) body.late = late === "yes";
  if ((half === "yes") !== Boolean(row.halfDay)) body.half_day = half === "yes";
  if (checkOut === "undo") body.clear_check_out = true;
  // Late follows the time unless you set it yourself; if the time moves and you didn't touch Late, the server works it out again.
  const changed = Object.keys(body).length > 2;

  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title={`Edit attendance — ${row.fullName}`}
      description={`${row.employeeCode} · ${date}. Developer correction; lateness is worked out again from the new time.`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" disabled={!changed || correct.isPending} onClick={() => correct.mutate(body, { onSuccess: onClose })}>
            {correct.isPending ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Input label="Check-in time" type="time" value={time} onChange={(e) => setTime(e.target.value)} hint="Moving the time works out Late again, unless you set Late below as well." />
        <Select
          label="Where"
          value={presence}
          onChange={(e) => setPresence(e.target.value)}
          options={[{ value: "office", label: "At office" }, { value: "away", label: "Away (not from office)" }]}
        />
        <Select
          label="Late"
          value={late}
          onChange={(e) => setLate(e.target.value)}
          options={[{ value: "no", label: "Not late" }, { value: "yes", label: "Late" }]}
        />
        <Select
          label="Half day"
          value={half}
          onChange={(e) => setHalf(e.target.value)}
          options={[{ value: "no", label: "Full day" }, { value: "yes", label: "Half day (payroll counts 0.5)" }]}
        />
        {row.checkOutAt && (
          <Select
            label="Check-out"
            value={checkOut}
            onChange={(e) => setCheckOut(e.target.value)}
            options={[{ value: "keep", label: `Keep (${fmtTime(row.checkOutAt)})` }, { value: "undo", label: "Undo check-out (they can check out again)" }]}
          />
        )}
      </div>
    </Modal>
  );
}

export function DailyView() {
  const canEdit = usePermission("attendance.edit");
  const [editing, setEditing] = useState<DayRow | null>(null);
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
      ["Date", "Employee ID", "Name", "Role", "Platform", "Status", "Late", "Check in", "Check out", "Hours", "Check-in presence", "Check-in location", "Latitude", "Longitude", "Distance to office (m)", "Check-out presence", "Check-out location"],
      rows.map((r) => [
        data.date, r.employeeCode, r.fullName, r.roles.join("/"), r.platform, r.status, r.late ? "Yes" : "",
        fmtTime(r.checkInAt), fmtTime(r.checkOutAt), (r.minutes / 60).toFixed(2),
        presenceText(r.checkInAt ? r.location : null), locationText(r.checkInAt ? r.location : null),
        r.location.latitude, r.location.longitude, r.location.distanceM,
        presenceText(r.checkOutAt ? r.checkOutLocation : null), locationText(r.checkOutAt ? r.checkOutLocation : null),
      ]),
    );
  }

  const s = data?.summary;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 rounded-2xl border border-surface-border bg-surface p-4 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-gray-700">Date</label>
              <input
                type="date"
                className="h-9 rounded-lg border border-surface-border bg-surface px-3 text-sm text-gray-900 shadow-xs outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                value={date}
                max={daysAgo(0)}
                onChange={(e) => e.target.value && setDate(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-1 rounded-xl bg-surface-subtle p-1 ring-1 ring-surface-border">
              {[["Today", 0], ["Yesterday", 1]].map(([l, n]) => {
                const active = date === daysAgo(n as number);
                return (
                  <button
                    key={l as string}
                    onClick={() => setDate(daysAgo(n as number))}
                    className={`rounded-lg px-3 py-1 text-xs font-semibold transition-all ${
                      active
                        ? "bg-gradient-to-r from-brand-600 via-brand-500 to-brand-600 text-white shadow-xs"
                        : "text-gray-600 hover:bg-surface hover:text-gray-900"
                    }`}
                  >
                    {l}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={exportCsv} disabled={!rows.length}>
              <IconDownload className="h-4 w-4" />
              Export CSV
            </Button>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-3">
            <SearchBox
              value={q}
              onChange={setQ}
              placeholder="Search employee name, ID, platform or region…"
              className="w-full"
            />
          </div>
          <Select
            label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value as "" | DayStatus)}
            placeholder="All statuses"
            options={STATUS_OPTIONS}
            className="[&_label]:sr-only"
          />
        </div>
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
                const present = r.status === "CHECKED_IN" || r.status === "CHECKED_OUT" || r.status === "NO_CHECKOUT" || r.status === "PRESENT";
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
                          {r.halfDay && r.status !== "ON_LEAVE" && <Badge tone="neutral">Half day</Badge>}
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
                      <td className="px-4 py-3">
                        <div className="flex items-start justify-between gap-2">
                          {present ? <LocationBadge location={r.location} /> : <span className="text-gray-300">—</span>}
                          {canEdit && present && (
                            <Button variant="secondary" size="sm" onClick={() => setEditing(r)}>Edit</Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <EditRecordModal row={editing} date={date} onClose={() => setEditing(null)} />
      {isFetching && !isLoading && <p className="-mt-3 text-xs text-gray-400">Refreshing…</p>}
      <p className="text-xs text-gray-400">
        Late means checking in after the work start time plus the grace period. Sundays are the weekly off. Locations come from the device and can be faked.
      </p>
    </div>
  );
}
