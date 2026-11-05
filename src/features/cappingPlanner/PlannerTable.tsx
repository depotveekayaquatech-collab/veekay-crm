import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Dropdown";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconSearch } from "@/components/ui/icons";
import { field } from "@/features/capping/styles";
import type { PlanRow } from "@/services/cappingPlanner";

type View = "all" | "selected" | "unselected" | "priority" | "excluded";
type Sort = "order" | "capacity" | "proposed" | "name";
const PAGE = 100;
const n = (v: number | null) => (v === null ? "—" : v.toLocaleString("en-IN"));

function matches(r: PlanRow, view: View): boolean {
  if (view === "selected") return r.selected;
  if (view === "unselected") return !r.selected && !r.excludeReason;
  if (view === "priority") return r.priorityRank !== null;
  if (view === "excluded") return r.excludeReason !== null;
  return true;
}

function compare(sort: Sort): (a: PlanRow, b: PlanRow) => number {
  if (sort === "name") return (a, b) => a.name.localeCompare(b.name);
  if (sort === "proposed") return (a, b) => b.proposed - a.proposed || b.capacity - a.capacity;
  if (sort === "order") return (a, b) => (a.selectionRank ?? 1e9) - (b.selectionRank ?? 1e9) || b.capacity - a.capacity;
  return (a, b) => b.capacity - a.capacity || a.name.localeCompare(b.name);
}

/** Every store with its recorded count, limit, remaining capacity and the plan's proposal. Recorded and planned values are labelled apart so a proposal is never read as supply. */
export function PlannerTable({ rows, allocationAllowed }: { rows: PlanRow[]; allocationAllowed: boolean }) {
  const [q, setQ] = useState("");
  const [view, setView] = useState<View>("selected");
  const [sort, setSort] = useState<Sort>("order");
  const [shown, setShown] = useState({ n: PAGE, sig: "" });

  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows
      .filter((r) => matches(r, view) && (!needle || r.name.toLowerCase().includes(needle) || r.outletId.toLowerCase().includes(needle) || r.crmCode.toLowerCase().includes(needle)))
      .sort(compare(sort));
  }, [rows, q, view, sort]);
  const sig = `${q}|${view}|${sort}`;
  const visible = shown.sig === sig ? shown.n : PAGE;     // back to the first page whenever the view changes

  return (
    <section className="flex flex-col gap-3" aria-label="Store-wise allocation preview">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-surface-border bg-surface p-3 shadow-card">
        <label className="relative min-w-[12rem] flex-1">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
          <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search store name or Outlet ID" aria-label="Search stores" />
        </label>
        <SelectField className={`${field} sm:w-48`} value={view} onChange={(e) => setView(e.target.value as View)} aria-label="Show">
          <option value="selected">Selected stores</option>
          <option value="all">All stores</option>
          <option value="unselected">Eligible, not selected</option>
          <option value="priority">Priority stores</option>
          <option value="excluded">Excluded stores</option>
        </SelectField>
        <SelectField className={`${field} sm:w-52`} value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
          <option value="order">Sort: selection order</option>
          <option value="capacity">Sort: highest capacity</option>
          <option value="proposed">Sort: proposed allocation</option>
          <option value="name">Sort: store name</option>
        </SelectField>
        <span className="ml-auto text-xs text-gray-500">{list.length.toLocaleString("en-IN")} of {rows.length.toLocaleString("en-IN")} stores</span>
      </div>

      {list.length === 0 ? (
        <EmptyState title="No stores to show" description={view === "selected" ? "No store was selected. Check the capacity, the store limit and the priority list." : "Change the search or the view."} />
      ) : (
        <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
          <table className="w-full min-w-[980px] border-collapse text-sm">
            <thead>
              <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold text-gray-500">
                <th className="border-b border-surface-border px-3 py-3 pl-4">Order</th>
                <th className="border-b border-surface-border px-3 py-3">Store</th>
                <th className="border-b border-surface-border px-3 py-3 text-right">Current count <span className="font-medium">(recorded)</span></th>
                <th className="border-b border-surface-border px-3 py-3 text-right">Monthly limit</th>
                <th className="border-b border-surface-border px-3 py-3 text-right">Available capacity</th>
                <th className="border-b border-surface-border bg-status-warning/10 px-3 py-3 text-right">Proposed allocation <span className="font-medium">(plan)</span></th>
                <th className="border-b border-surface-border bg-status-warning/10 px-3 py-3 text-right">Final planned count <span className="font-medium">(plan)</span></th>
              </tr>
            </thead>
            <tbody>
              {list.slice(0, visible).map((r) => (
                <tr key={r.storeId} className="border-b border-surface-border/60 hover:bg-surface-subtle/50">
                  <td data-label="Order" className="px-3 py-3 pl-4 tabular-nums text-gray-600">
                    {r.selectionRank ?? "—"}
                    {r.priorityRank !== null && <div className="mt-0.5"><Badge tone="info">Priority #{r.priorityRank}</Badge></div>}
                  </td>
                  <td data-label="Store" className="max-w-[280px] px-3 py-3">
                    <p className="break-words font-semibold text-gray-900">{r.name}</p>
                    <p className="break-all text-xs text-gray-500">{r.outletId || "no Outlet ID"} · {r.crmCode}{r.city ? ` · ${r.city}` : ""}{r.project !== "zepto" ? ` · ${r.project}` : ""}</p>
                  </td>
                  <td data-label="Current count" className="px-3 py-3 text-right tabular-nums">{n(r.used)}</td>
                  <td data-label="Monthly limit" className="px-3 py-3 text-right tabular-nums">{n(r.monthlyLimit)}</td>
                  <td data-label="Available capacity" className="px-3 py-3 text-right tabular-nums">
                    {r.excludeReason ? <Badge tone="neutral">{r.excludeReason}</Badge> : r.overBy > 0 ? <span className="text-status-danger">over by {n(r.overBy)}</span> : <span className="font-semibold">{n(r.capacity)}</span>}
                  </td>
                  <td data-label="Proposed allocation" className="bg-status-warning/5 px-3 py-3 text-right font-semibold tabular-nums">{allocationAllowed ? n(r.proposed) : "—"}</td>
                  <td data-label="Final planned count" className="bg-status-warning/5 px-3 py-3 text-right tabular-nums">{allocationAllowed ? n(r.finalPlanned) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {list.length > visible && (
        <div className="flex justify-center">
          <Button variant="secondary" onClick={() => setShown({ n: visible + PAGE, sig })}>Show {Math.min(PAGE, list.length - visible)} more ({list.length - visible} left)</Button>
        </div>
      )}
    </section>
  );
}
