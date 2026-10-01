import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { usePermission } from "@/hooks/usePermission";
import { DailyView } from "@/features/attendance/DailyView";
import { MonthlyView } from "@/features/attendance/MonthlyView";
import { MyAttendance } from "@/features/attendance/MyAttendance";
import { OfficesView } from "@/features/attendance/OfficesView";

type Tab = "daily" | "monthly" | "offices" | "me";

/**
 * Attendance from sign-in / sign-out. Admins (attendance.view) get the team views;
 * everyone else just sees their own record.
 */
export function AttendancePage() {
  const canView = usePermission("attendance.view");
  const [params, setParams] = useSearchParams();

  const tabs: { id: Tab; label: string }[] = canView
    ? [
        { id: "daily", label: "Daily" },
        { id: "monthly", label: "Monthly" },
        { id: "offices", label: "Offices" },
      ]
    : [{ id: "me", label: "My attendance" }];
  const requested = params.get("tab") as Tab | null;
  const tab: Tab = tabs.some((t) => t.id === requested) ? (requested as Tab) : tabs[0].id;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Attendance"
        subtitle={
          canView
            ? "Sign-in and sign-out times for employees and accounts staff, and where each person signed in from. Admins are not tracked."
            : "Your sign-in and sign-out times."
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
      {tab === "daily" && <DailyView />}
      {tab === "monthly" && <MonthlyView />}
      {tab === "offices" && <OfficesView />}
      {tab === "me" && <MyAttendance />}
    </div>
  );
}
