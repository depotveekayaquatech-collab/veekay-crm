import { PageHeader } from "@/components/layout/PageHeader";
import { HistoryPanel } from "@/features/zero/HistoryPanel";
import { MonthlyPanel } from "@/features/zero/MonthlyPanel";
import { StreaksPanel } from "@/features/zero/StreaksPanel";
import { WeeklyPanel } from "@/features/zero/WeeklyPanel";
import { useBadge } from "@/features/zero/api";
import { useZeroFilters } from "@/features/zero/useZeroFilters";
import { usePermission } from "@/hooks/usePermission";

type Tab = "streaks" | "weekly" | "monthly" | "history";

/**
 * Zero Review: a weekly check that no store is silently stuck at zero, and a monthly verification of last month's data. A zero is a day somebody entered 0;
 * a day with no entry is "unmarked", reported separately. Its own filters live in the URL, so a view can be bookmarked or sent to a team lead.
 */
export function ZeroReviewPage() {
  const f = useZeroFilters();
  const canReview = usePermission("zero.review");
  const badge = useBadge(canReview);
  const requested = f.params.get("tab") as Tab | null;
  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "streaks", label: "Zero Streaks" },
    { id: "weekly", label: "Weekly Review", count: badge.data?.weekly },
    { id: "monthly", label: "Monthly Verification", count: badge.data?.months },
    { id: "history", label: "History & Log" },
  ];
  const tab: Tab = tabs.some((t) => t.id === requested) ? (requested as Tab) : "streaks";
  const go = (id: Tab) => { const n = new URLSearchParams(f.params); n.set("tab", id); n.delete("page"); f.setParams(n, { replace: true }); };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Zero Review" subtitle="Find stores stuck at zero, review them every Saturday, and verify last month's data. Employees see their own stores; Team Leads, Reviewers and administrators can review." />
      <div role="tablist" aria-label="Zero Review" className="flex flex-wrap gap-1.5">
        {tabs.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => go(t.id)}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors ${tab === t.id ? "bg-brand-500 text-white shadow-sm" : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"}`}>
            {t.label}
            {t.count ? <span className={`rounded-full px-1.5 py-px text-[11px] font-bold tabular-nums ${tab === t.id ? "bg-white/25 text-white" : "bg-status-danger text-white"}`} aria-label={`${t.count} waiting`}>{t.count > 99 ? "99+" : t.count}</span> : null}
          </button>
        ))}
      </div>
      {tab === "streaks" && <StreaksPanel f={f} />}
      {tab === "weekly" && <WeeklyPanel f={f} />}
      {tab === "monthly" && <MonthlyPanel f={f} />}
      {tab === "history" && <HistoryPanel f={f} />}
    </div>
  );
}
