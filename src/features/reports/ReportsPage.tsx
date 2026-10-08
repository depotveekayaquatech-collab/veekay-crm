import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { DeliveryReport } from "@/features/reports/DeliveryReport";
import { TestReportsTab } from "@/features/reports/TestReportsTab";

type Tab = "test" | "delivery";

const TABS: { id: Tab; label: string }[] = [
  { id: "test", label: "Test Reports" },
  { id: "delivery", label: "Delivery Reports" },
];

export function ReportsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "test" ? "test" : "delivery";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Reports"
        subtitle="Test reports (valid for 6 months, per state) and delivery reports in one place."
        action={
          <div role="tablist" aria-label="Report type" className="flex gap-1 rounded-xl bg-surface-muted p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setParams(t.id === "delivery" ? {} : { tab: t.id }, { replace: true })}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition-all ${
                  tab === t.id ? "bg-surface text-heading shadow-sm ring-1 ring-surface-border" : "text-gray-500 hover:text-gray-800"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        }
      />
      {tab === "test" ? <TestReportsTab /> : <DeliveryReport />}
    </div>
  );
}
