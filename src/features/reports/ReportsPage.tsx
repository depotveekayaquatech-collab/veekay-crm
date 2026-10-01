import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { DeliveryReport } from "@/features/reports/DeliveryReport";
import { IconReport } from "@/components/ui/icons";

type Tab = "test" | "delivery";

const TABS: { id: Tab; label: string }[] = [
  { id: "test", label: "Test Reports" },
  { id: "delivery", label: "Delivery Reports" },
];

function TestReports() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-surface-border bg-white px-6 py-20 text-center shadow-card">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-aqua-50 text-aqua-600">
        <IconReport className="h-7 w-7" />
      </span>
      <p className="text-lg font-bold text-ink-900">Test reports are coming soon</p>
      <p className="max-w-md text-sm text-gray-500">
        This tab is reserved for test reports. Nothing to show yet — delivery numbers are in the Delivery Reports tab.
      </p>
    </div>
  );
}

export function ReportsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "test" ? "test" : "delivery";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Reports"
        subtitle="Test and delivery reports in one place."
        action={
          <div role="tablist" aria-label="Report type" className="flex gap-1 rounded-xl bg-surface-muted p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setParams(t.id === "delivery" ? {} : { tab: t.id }, { replace: true })}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition-all ${
                  tab === t.id ? "bg-white text-ink-900 shadow-sm ring-1 ring-surface-border" : "text-gray-500 hover:text-gray-800"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        }
      />
      {tab === "test" ? <TestReports /> : <DeliveryReport />}
    </div>
  );
}
