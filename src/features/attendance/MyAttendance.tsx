import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconClock, IconMapPin } from "@/components/ui/icons";
import { LocationBadge, StatusBadge } from "@/features/attendance/parts";
import { fmtDay, fmtMinutes, fmtTime } from "@/features/attendance/format";
import { LEAVE_LABEL, useCheckMutations, useMyAttendance, useTodayStatus, type TodayStatus } from "@/features/attendance/api";
import { getDeviceLocation } from "@/lib/geo";

const field = "h-10 rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

function thisMonth(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`;
}

function useClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/** The Check in / Check out card. Location is asked for here — and only here — when the person taps the button. */
function CheckCard({ today }: { today: TodayStatus }) {
  const now = useClock();
  const { checkIn, checkOut } = useCheckMutations();
  const [locating, setLocating] = useState(false);
  const [noLocation, setNoLocation] = useState<"in" | "out" | null>(null);
  const busy = locating || checkIn.isPending || checkOut.isPending;

  async function go(kind: "in" | "out", withoutLocation = false) {
    setNoLocation(null);
    let reading: { latitude?: number; longitude?: number; accuracy?: number } = {};
    if (!withoutLocation) {
      setLocating(true);
      const loc = await getDeviceLocation();
      setLocating(false);
      if (!loc) {
        setNoLocation(kind);
        return;
      }
      reading = { latitude: loc.latitude, longitude: loc.longitude, accuracy: loc.accuracy };
    }
    try {
      await (kind === "in" ? checkIn : checkOut).mutateAsync(reading);
    } catch {
      /* the API layer already showed the reason */
    }
  }

  const greeting = now.getHours() < 12 ? "Good morning" : now.getHours() < 17 ? "Good afternoon" : "Good evening";
  const done = today.checkedOut;
  const onLeave = today.onLeave && !today.checkedIn;

  return (
    <section className="relative overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          backgroundImage:
            "radial-gradient(520px circle at 0% 0%, rgba(47,111,237,0.10), transparent 60%), radial-gradient(420px circle at 100% 100%, rgba(42,169,189,0.12), transparent 60%)",
        }}
      />
      <div className="relative grid gap-6 p-5 sm:p-7 md:grid-cols-[1fr_auto] md:items-center">
        <div>
          <p className="text-sm font-semibold text-gray-500">{greeting}</p>
          <p className="mt-1 flex items-baseline gap-3">
            <span className="text-[2.6rem] font-bold leading-none tabular-nums text-heading">
              {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
            <span className="text-sm text-gray-500">{now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</span>
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {today.checkedIn ? (
              <>
                <Badge tone="success">Checked in {fmtTime(today.checkInAt)}</Badge>
                {today.late && <Badge tone="warning">Late</Badge>}
                {done && <Badge tone="info">Checked out {fmtTime(today.checkOutAt)}</Badge>}
                {today.minutes != null && <span className="text-xs text-gray-500">{fmtMinutes(today.minutes)} {done ? "worked" : "so far"}</span>}
              </>
            ) : onLeave ? (
              <Badge tone="info">On {LEAVE_LABEL[today.onLeave!.leaveType].toLowerCase()} today</Badge>
            ) : today.isWeeklyOff ? (
              <Badge tone="neutral">Weekly off</Badge>
            ) : (
              <span className="text-sm text-gray-500">
                You haven't checked in yet. Work starts at {today.workStart}; after a {today.graceMinutes}-minute grace you're marked late.
              </span>
            )}
          </div>
          {today.checkInLocation && (
            <div className="mt-3 flex items-center gap-2 text-xs text-gray-500">
              <IconMapPin className="h-3.5 w-3.5" /> Check-in: <LocationBadge location={today.checkInLocation} />
            </div>
          )}
          {today.checkOutLocation && (
            <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
              <IconMapPin className="h-3.5 w-3.5" /> Check-out: <LocationBadge location={today.checkOutLocation} />
            </div>
          )}
        </div>

        <div className="flex flex-col items-stretch gap-2 md:w-60">
          {!today.checkedIn && (
            <Button size="lg" onClick={() => void go("in")} isLoading={busy}>
              <IconClock className="h-4 w-4" />
              {locating ? "Getting your location…" : "Check in"}
            </Button>
          )}
          {today.checkedIn && !done && (
            <Button size="lg" variant="danger" onClick={() => void go("out")} isLoading={busy}>
              <IconClock className="h-4 w-4" />
              {locating ? "Getting your location…" : "Check out"}
            </Button>
          )}
          {done && <p className="text-center text-sm font-semibold text-status-success">All done for today ✓</p>}
          {!done && <p className="text-center text-[11px] text-gray-400">Your location is read only when you tap this button.</p>}
        </div>
      </div>

      {noLocation && (
        <div className="relative flex flex-wrap items-center gap-3 border-t border-status-warning/25 bg-status-warning-soft/60 px-5 py-3 text-sm sm:px-7">
          <span className="text-gray-700">
            We couldn't read your location — allow location access for this site in your browser, or continue without it.
          </span>
          <span className="ml-auto flex gap-2">
            <Button size="sm" variant="secondary" onClick={() => void go(noLocation)}>Try again</Button>
            <Button size="sm" variant="secondary" onClick={() => void go(noLocation, true)}>
              {noLocation === "in" ? "Check in" : "Check out"} without location
            </Button>
          </span>
        </div>
      )}
    </section>
  );
}

/** Today's check in / out, plus your month: every day's times, leave and absences. */
export function MyAttendance() {
  const { data: today, isLoading: todayLoading } = useTodayStatus();
  const [month, setMonth] = useState(thisMonth());
  const { data, isLoading, isError, refetch } = useMyAttendance(month);

  const me = data?.rows[0];
  const days = me ? Object.entries(me.days).sort(([a], [b]) => (a < b ? 1 : -1)) : [];

  return (
    <div className="flex flex-col gap-6">
      {todayLoading && <Skeleton className="h-44" />}
      {today && today.eligible && <CheckCard today={today} />}

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Month
          <input type="month" className={field} value={month} max={thisMonth()} onChange={(e) => e.target.value && setMonth(e.target.value)} />
        </label>
      </div>

      {me && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {[
            ["Days present", me.daysPresent, "brand"],
            ["Hours worked", (me.totalMinutes / 60).toFixed(1), "aqua"],
            ["Late", me.lateDays, me.lateDays ? "warning" : "success"],
            ["On leave", me.leaveDays, "brand"],
            ["Absent", me.absentDays, me.absentDays ? "warning" : "success"],
          ].map(([t, v, tone]) => (
            <div key={t as string} className={`tile tile-${tone} rounded-xl border border-surface-border bg-surface p-4 shadow-card`}>
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{t}</p>
              <p className="mt-1.5 text-[1.6rem] font-bold leading-none tabular-nums text-heading">{v}</p>
            </div>
          ))}
        </div>
      )}

      {isLoading && <Skeleton className="h-56" />}
      {isError && <ErrorState message="Couldn't load your attendance." onRetry={() => refetch()} />}
      {data && days.length === 0 && <EmptyState title="Nothing this month yet" description="Your check-ins, check-outs and leave will appear here." />}

      {days.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3">Date</th>
                <th className="px-3 py-3">Check in</th>
                <th className="px-3 py-3">Check out</th>
                <th className="px-3 py-3 text-right">Hours</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-4 py-3">Location</th>
              </tr>
            </thead>
            <tbody>
              {days.map(([d, e]) => (
                <tr key={d} className="border-t border-surface-border/70 align-top">
                  <td className="px-4 py-3 font-medium text-gray-900">{fmtDay(d)}</td>
                  <td className="px-3 py-3 tabular-nums">
                    {fmtTime(e.checkInAt)} {e.late && <Badge tone="warning">Late</Badge>}
                  </td>
                  <td className="px-3 py-3 tabular-nums">
                    {e.checkOutAt ? fmtTime(e.checkOutAt) : e.status === "CHECKED_IN" ? <span className="text-xs text-gray-400">still in</span> : e.status === "NO_CHECKOUT" ? <span className="text-xs text-status-warning">didn't check out</span> : "—"}
                  </td>
                  <td className="px-3 py-3 text-right font-semibold tabular-nums text-heading">{e.status === "ON_LEAVE" ? "—" : fmtMinutes(e.minutes)}</td>
                  <td className="px-3 py-3">
                    <StatusBadge status={e.status} />
                    {e.status === "ON_LEAVE" && e.leaveType && <div className="mt-0.5 text-[11px] text-gray-500">{LEAVE_LABEL[e.leaveType]}{e.halfDay ? " · half day" : ""}</div>}
                  </td>
                  <td className="px-4 py-3">{e.status === "ON_LEAVE" ? "—" : <LocationBadge location={e.location} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
