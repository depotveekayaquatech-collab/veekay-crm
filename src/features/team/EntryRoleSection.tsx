import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";
import type { Employee } from "@/types/employee";

const LEVELS = [
  { value: "entry_contributor", label: "Entry Contributor (default) — sees only their own entries" },
  { value: "team_lead", label: "Team Lead — sees and corrects their team's entries" },
  { value: "entry_reviewer", label: "Entry Reviewer — audits and flags every entry, changes nothing" },
];

/** Administrators only: this person's level in the entry hierarchy, and the Team Lead they report to. Saved on its own; takes effect on their next request. */
export function EntryRoleSection({ employee }: { employee: Employee }) {
  const qc = useQueryClient();
  const current = employee.roles.includes("entry_reviewer") ? "entry_reviewer" : employee.roles.includes("team_lead") ? "team_lead" : "entry_contributor";
  const [level, setLevel] = useState(current);
  const [lead, setLead] = useState(employee.reportsToId ?? "");
  const leads = useQuery({ queryKey: ["entry-leads"], queryFn: () => apiRequest<{ id: string; name: string; code: string }[]>("/entries/leads", { silent: true }) });

  const save = useMutation({
    mutationFn: () =>
      apiRequest(`/employees/${employee.id}/entry-role`, {
        method: "PUT",
        body: { level, ...(level === "team_lead" || level === "entry_reviewer" ? { reports_to_id: null } : { reports_to_id: lead || null }) },
      }),
    onSuccess: () => {
      pushToast("Saved. It applies from their next action; nothing else about the account changed.", "success");
      void qc.invalidateQueries({ queryKey: ["employees"] });
      void qc.invalidateQueries({ queryKey: ["entry-leads"] });
    },
  });

  const options = (leads.data ?? []).filter((l) => l.id !== employee.id).map((l) => ({ value: l.id, label: `${l.name} (${l.code})` }));
  const dirty = level !== current || (level === "entry_contributor" && lead !== (employee.reportsToId ?? ""));

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface-subtle/60 p-4">
      <div>
        <p className="text-sm font-bold text-heading">Entry role</p>
        <p className="text-xs text-gray-500">Who may see and correct this person's entries. Everyone starts as an Entry Contributor.</p>
      </div>
      <Select label="Level" value={level} onChange={(e) => setLevel(e.target.value)} options={LEVELS} />
      {level === "entry_contributor" && (
        <Select
          label="Reports to (Team Lead)"
          value={lead}
          onChange={(e) => setLead(e.target.value)}
          options={[{ value: "", label: "No Team Lead" }, ...options]}
          placeholder="No Team Lead"
        />
      )}
      <div>
        <Button type="button" variant="secondary" size="sm" isLoading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>
          Save entry role
        </Button>
      </div>
    </div>
  );
}
