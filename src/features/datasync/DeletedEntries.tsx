import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Table, Td, Th } from "@/components/ui/Table";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";
import { apiRequest } from "@/services/api";

type State = "RESTORABLE" | "ALREADY_THERE" | "STORE_GONE" | "RESTORED";

interface DeletedItem {
  id: string;
  orderDate: string;
  storeCode: string | null;
  storeName: string | null;
  bottles: number | null;
  cashAdjustment: number | null;
  source: string | null;
  markedBy: string | null;
  deletedAt: string;
  restoredAt: string | null;
  state: State;
}

interface DeletedList {
  summary: { restorable: number; alreadyThere: number; storeGone: number; restored: number };
  items: DeletedItem[];
  truncated: boolean;
}

interface RestoreResult {
  restorable: number;
  restored: number;
  alreadyThere: number;
  storeGone: number;
}

const BASE = "/developer/order-audit/deleted";
const STATE: Record<State, { label: string; tone: "success" | "info" | "warning" | "neutral"; hint: string }> = {
  RESTORABLE: { label: "Can be restored", tone: "success", hint: "Deleted; nothing is there now." },
  ALREADY_THERE: { label: "Entry exists now", tone: "neutral", hint: "The day has an entry again, so this copy is left alone." },
  STORE_GONE: { label: "Store is gone", tone: "warning", hint: "Add the store again (same platform and code) and it can be restored." },
  RESTORED: { label: "Restored", tone: "info", hint: "Put back." },
};
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" });

/** Developer: order entries that were deleted (any way: an admin clearing a day, removing stores, a tool, SQL), as the database kept them, with a one-click restore. */
export function DeletedEntries({ start, end }: { start: string; end: string }) {
  const [list, setList] = useState<DeletedList | null>(null);
  const [showRestored, setShowRestored] = useState(false);
  // Employee-marked entries only: leaves out what an order-sheet import or an admin wrote. On by default.
  const [employeeOnly, setEmployeeOnly] = useState(true);

  const load = useMutation({
    mutationFn: async () => camelize<DeletedList>(await apiRequest(`${BASE}?start=${start}&end=${end}${showRestored ? "&include_restored=true" : ""}${employeeOnly ? "&employee_only=true" : ""}`)),
    onSuccess: setList,
  });
  const restore = useMutation({
    mutationFn: async (ids: string[] | null) =>
      camelize<RestoreResult>(await apiRequest(`${BASE}/restore`, { method: "POST", body: ids ? { ids, dry_run: false, employee_only: employeeOnly } : { start, end, dry_run: false, employee_only: employeeOnly } })),
    onSuccess: (r) => {
      pushToast(`${r.restored} entr${r.restored === 1 ? "y" : "ies"} restored.`, "success");
      load.mutate();
    },
  });

  const restorable = list?.summary.restorable ?? 0;
  return (
    <div className="flex flex-col gap-3 border-t border-surface-border pt-4">
      <div className="flex flex-wrap items-center gap-3">
        <h4 className="text-sm font-bold text-gray-900">Deleted entries</h4>
        <p className="text-xs text-gray-500">Every deleted entry is kept by the database, whatever deleted it, and can be put back. Uses the dates above.</p>
        <label className="ml-auto flex items-center gap-2 text-xs text-gray-700">
          <input type="checkbox" className="h-4 w-4" checked={employeeOnly} onChange={(e) => { setEmployeeOnly(e.target.checked); setList(null); }} />
          Only entries employees marked (skip order-sheet imports and admin entries)
        </label>
        <label className="flex items-center gap-2 text-xs text-gray-700">
          <input type="checkbox" className="h-4 w-4" checked={showRestored} onChange={(e) => setShowRestored(e.target.checked)} />
          Include ones already restored
        </label>
        <Button variant="secondary" onClick={() => load.mutate()} isLoading={load.isPending}>Show deleted entries</Button>
        {restorable > 0 && (
          <Button
            onClick={() => {
              if (window.confirm(`Restore ${restorable} deleted entr${restorable === 1 ? "y" : "ies"}${employeeOnly ? " marked by employees" : " (including order-sheet imports and admin entries)"}? Days that already have an entry are left alone.`)) restore.mutate(null);
            }}
            isLoading={restore.isPending}
          >
            Restore all {restorable}
          </Button>
        )}
      </div>

      {list && (list.items.length === 0 ? (
        <p role="status" className="rounded-xl border border-status-success/30 bg-status-success/10 px-4 py-3 text-sm text-gray-800">No order entries were deleted in this period.</p>
      ) : (
        <>
          <p className="text-sm text-gray-700">
            Can be restored <b>{list.summary.restorable}</b> · Store is gone <b>{list.summary.storeGone}</b> · Entry exists now <b>{list.summary.alreadyThere}</b>
            {showRestored ? <> · Restored <b>{list.summary.restored}</b></> : null}
          </p>
          <Table>
            <thead>
              <tr><Th>Day</Th><Th>Store</Th><Th className="text-right">Bottles</Th><Th>Entered by</Th><Th>Deleted</Th><Th>State</Th><Th /></tr>
            </thead>
            <tbody>
              {list.items.map((i) => (
                <tr key={i.id}>
                  <Td className="whitespace-nowrap">{day(i.orderDate)}</Td>
                  <Td><p className="font-medium text-gray-900">{i.storeName ?? "—"}</p><p className="text-xs text-gray-500">{i.storeCode}</p></Td>
                  <Td className="text-right tabular-nums">{i.bottles ?? "—"}</Td>
                  <Td>{i.markedBy ?? (i.source === "admin" ? "Admin / import" : "—")}</Td>
                  <Td className="whitespace-nowrap text-xs text-gray-600">{new Date(i.deletedAt).toLocaleString("en-IN")}</Td>
                  <Td><Badge tone={STATE[i.state].tone}>{STATE[i.state].label}</Badge><p className="mt-1 text-xs text-gray-500">{STATE[i.state].hint}</p></Td>
                  <Td className="text-right">{i.state === "RESTORABLE" && <Button size="sm" variant="secondary" onClick={() => restore.mutate([i.id])} isLoading={restore.isPending}>Restore</Button>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          {list.truncated && <p className="text-xs text-gray-500">Showing the first 1,000. Narrow the dates to see the rest.</p>}
        </>
      ))}
    </div>
  );
}
