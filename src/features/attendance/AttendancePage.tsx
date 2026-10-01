import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { usePermission } from "@/hooks/usePermission";
import { DailyView } from "@/features/attendance/DailyView";
import { LeavePanel } from "@/features/attendance/LeavePanel";
import { LeaveRequestsView } from "@/features/attendance/LeaveRequestsView";
import { MonthlyView } from "@/features/attendance/MonthlyView";
import { MyAttendance } from "@/features/attendance/MyAttendance";
import { OfficesView } from "@/features/attendance/OfficesView";
import { useAllLeaves, useTodayStatus } from "@/features/attendance/api";

type Tab = "me" | "leave" | "daily" | "monthly" | "requests" | "offices";

/**
 * Attendance. Employees and accounts staff check in / out and apply for leave here (this is the only place a
 * location is asked for). Admins (attendance.view) get the team views, and leave approvals (leave.review).
 */
export function AttendancePage() {
  const canView = usePermission("attendance.view");
  const canReview = usePermission("leave.review");
  const { data: today } = useTodayStatus();
  const { data: pending } = useAllLeaves("PENDING", "", canReview);
  const [params, setParams] = useSearchParams();

  const eligible = Boolean(today?.eligible);
  const tabs: { id: Tab; label: string }[] = [
    ...(eligible ? [{ id: "me" as Tab, label: "My attendance" }, { id: "leave" as Tab, label: "My leave" }] : []),
    ...(canView ? [{ id: "daily" as Tab, label: "Daily" }, { id: "monthly" as Tab, label: "Monthly" }] : []),
    ...(canReview ? [{ id: "requests" as Tab, label: pending?.pending ? `Leave requests (${pending.pending})` : "Leave requests" }] : []),
    ...(canView ? [{ id: "offices" as Tab, label: "Offices" }] : []),
  ];
  const requested = params.get("tab") as Tab | null;
  const tab: Tab | null = tabs.some((t) => t.id === requested) ? (requested as Tab) : (tabs[0]?.id ?? null);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Attendance"
        subtitle={
          canView
            ? "Check-ins and check-outs for employees and accounts staff, where each person was, and leave. Admins are not tracked."
            : "Check in when you start, check out when you finish, and apply for leave."
        }
        action={
          tabs.length > 1 && (
            <div role="tablist" aria-label="Attendance views" className="flex flex-wrap gap-1 rounded-xl bg-surface-muted p-1">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => setParams(t.id === tabs[0].id ? {} : { tab: t.id }, { replace: true })}
                  className={`rounded-lg px-4 py-2 text-sm font-semibold transition-all ${
                    tab === t.id ? "bg-white text-ink-900 shadow-sm ring-1 ring-surface-border" : "text-gray-500 hover:text-gray-800"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          )
        }
      />
      {!tab && (
        <p className="rounded-xl border border-dashed border-surface-border bg-white px-6 py-12 text-center text-sm text-gray-500">
          Attendance is not tracked for your account.
        </p>
      )}
      {tab === "me" && <MyAttendance />}
      {tab === "leave" && <LeavePanel />}
      {tab === "daily" && <DailyView />}
      {tab === "monthly" && <MonthlyView />}
      {tab === "requests" && <LeaveRequestsView />}
      {tab === "offices" && <OfficesView />}
    </div>
  );
}
