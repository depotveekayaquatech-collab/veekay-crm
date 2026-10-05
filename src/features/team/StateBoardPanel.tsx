import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { usePartners } from "@/features/stores/useStores";
import { useStateBoard, useTeamMutations } from "@/features/team/useTeam";

export function StateBoardPanel() {
  const { data: partners = [] } = usePartners();
  const [partner, setPartner] = useState("zepto");
  const [employeeId, setEmployeeId] = useState("");
  const { data: board, isLoading } = useStateBoard(partner);
  const { assignState, unassignState } = useTeamMutations();

  const partnerId = partners.find((p) => p.slug === partner)?.id ?? "";

  return (
    <div className="rounded-lg border border-surface-border bg-surface p-4 shadow-card">
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">State assignment</h3>
          <p className="text-xs text-gray-500">Split a platform's states across employees.</p>
        </div>
        <div className="ml-auto flex gap-2">
          <Select
            label=""
            aria-label="Platform"
            value={partner}
            onChange={(e) => setPartner(e.target.value)}
            options={partners.map((p) => ({ value: p.slug, label: p.name }))}
          />
        </div>
      </div>

      {isLoading && <Skeleton className="h-40" />}
      {board && (
        <>
          <p className="mb-3 text-xs text-gray-500">
            <strong>{board.unassigned_state_count}</strong> unassigned ({board.unassigned_store_count} stores)
            {" · "}
            <strong>{board.assigned_state_count}</strong> assigned ({board.assigned_store_count} stores)
          </p>

          <Select
            label="Assign selected states to"
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            placeholder="Pick an employee"
            options={board.employees.map((e) => ({ value: e.id, label: `${e.name} (${e.employee_code})` }))}
            className="sm:max-w-xs"
          />

          <div className="mt-3 grid gap-4 lg:grid-cols-2">
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">Unassigned</p>
              <div className="max-h-56 space-y-1 overflow-auto">
                {board.unassigned.length === 0 && <p className="text-sm text-gray-400">All states assigned.</p>}
                {board.unassigned.map((s) => (
                  <div key={s.state} className="flex items-center justify-between rounded-md border border-surface-border px-3 py-2 text-sm">
                    <span>{s.state} <span className="text-gray-400">· {s.store_count}</span></span>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={!employeeId}
                      onClick={() => assignState.mutate({ partnerId, state: s.state, employeeId })}
                    >
                      Assign
                    </Button>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">Assigned</p>
              <div className="max-h-56 space-y-1 overflow-auto">
                {board.assigned.length === 0 && <p className="text-sm text-gray-400">None yet.</p>}
                {board.assigned.map((s) => (
                  <div key={s.state} className="flex items-center justify-between rounded-md border border-surface-border px-3 py-2 text-sm">
                    <span>
                      {s.state} <span className="text-gray-400">→ {s.employee_name}</span>
                    </span>
                    <Button size="sm" variant="ghost" onClick={() => s.assignment_id && unassignState.mutate(s.assignment_id)}>
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
