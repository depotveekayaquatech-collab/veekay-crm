import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { PlanIssue } from "@/services/cappingPlanner";

const PAGE = 50;
const TONE = { error: "danger", warning: "warning", info: "info" } as const;
const TITLE: Record<string, string> = {
  duplicate_record: "Duplicate store records",
  invalid_limit: "Invalid monthly limits",
  missing_outlet_id: "Missing Outlet IDs",
  missing_capping: "Missing capping",
  over_cap: "Over their limit (negative remaining capacity)",
  shared_outlet_id: "Outlet ID shared by different stores",
  same_name_other_outlet: "Same name, different Outlet IDs",
  no_supply_records: "No supply records this month",
  zero_limit: "Capping set to 0",
};

/** What the data checks found, grouped by kind. Errors keep a store out of the capacity; warnings and notes do not. */
export function PlannerIssues({ issues }: { issues: PlanIssue[] }) {
  const groups = useMemo(() => {
    const by = new Map<string, PlanIssue[]>();
    for (const i of issues) by.set(i.code, [...(by.get(i.code) ?? []), i]);
    const rank = { error: 0, warning: 1, info: 2 } as const;
    return [...by.entries()].sort((a, b) => rank[a[1][0]!.severity] - rank[b[1][0]!.severity] || b[1].length - a[1].length);
  }, [issues]);
  const [open, setOpen] = useState<string | null>(null);
  const [shown, setShown] = useState(PAGE);

  if (issues.length === 0) return <section className="rounded-xl border border-status-success/40 bg-status-success/5 p-4 text-sm text-gray-700 shadow-card">No data issues found for these stores.</section>;
  return (
    <section className="flex flex-col gap-2" aria-label="Validation issues">
      <h2 className="text-sm font-bold text-gray-900">Validation issues <Badge tone="warning">{issues.length.toLocaleString("en-IN")}</Badge></h2>
      <ul className="flex flex-col gap-2">
        {groups.map(([code, list]) => (
          <li key={code} className="rounded-xl border border-surface-border bg-surface shadow-card">
            <button type="button" aria-expanded={open === code} onClick={() => { setOpen(open === code ? null : code); setShown(PAGE); }} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
              <span className="text-sm font-semibold text-gray-900">{TITLE[code] ?? code}</span>
              <Badge tone={TONE[list[0]!.severity]}>{list.length.toLocaleString("en-IN")}</Badge>
            </button>
            {open === code && (
              <div className="border-t border-surface-border px-4 py-3">
                <ul className="flex flex-col gap-2">
                  {list.slice(0, shown).map((i) => (
                    <li key={`${i.storeId}-${i.message}`} className="text-sm">
                      <p className="break-words font-medium text-gray-900">{i.name} <span className="text-xs font-normal text-gray-500">{i.outletId || "no Outlet ID"} · {i.crmCode}</span></p>
                      <p className="text-xs text-gray-600">{i.message}</p>
                    </li>
                  ))}
                </ul>
                {list.length > shown && <div className="mt-3"><Button variant="secondary" size="sm" onClick={() => setShown((v) => v + PAGE)}>Show more ({list.length - shown} left)</Button></div>}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
