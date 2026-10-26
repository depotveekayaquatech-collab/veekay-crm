import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";

interface Person { id: string; name: string; code: string }
interface Platform {
  id: string; name: string; slug: string; employees: number;
  reviewers: Person[];
  team_leads: (Person & { employees: Person[] })[];
  unassigned: Person[];
  under_other_platform_lead: (Person & { team_lead: Person })[];
}
interface Hierarchy { admins: Person[]; reviewers_all_platforms: Person[]; platforms: Platform[] }

const names = (people: Person[]) => (people.length ? people.map((p) => p.name).join(", ") : null);

function Level({ label, tone, children }: { label: string; tone: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${tone}`}>{label}</span>
      <span className="text-sm text-gray-800">{children}</span>
    </div>
  );
}

/** Everyone without a Team Lead on one platform, ready to be put under one in a single step: their entries would otherwise wait for nobody. */
function Unassigned({ platform }: { platform: Platform }) {
  const qc = useQueryClient();
  const [lead, setLead] = useState(platform.team_leads[0]?.id ?? "");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const assign = useMutation({
    mutationFn: (ids: string[]) => apiRequest<{ assigned: number; team_lead: { name: string } }>("/entries/assign-team", { method: "POST", silent: true, body: { team_lead_id: lead, employee_ids: ids } }),
    onSuccess: (r) => {
      pushToast(`${r.assigned} employee${r.assigned === 1 ? "" : "s"} now report to ${r.team_lead.name}.`, "success");
      setPicked(new Set());
      for (const k of ["entry-hierarchy", "employees", "entry-leads"]) void qc.invalidateQueries({ queryKey: [k] });
    },
    onError: (e) => pushToast(e instanceof Error ? e.message : "That didn't work.", "error"),
  });
  const people = platform.unassigned;
  if (people.length === 0) return null;
  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const ids = picked.size ? [...picked] : people.map((p) => p.id);

  return (
    <div className="rounded-xl border border-status-warning/40 bg-status-warning-soft/50 p-4">
      <p className="text-sm font-bold text-status-warning">{people.length} without a Team Lead</p>
      <p className="mt-0.5 text-xs text-gray-600">Nobody verifies these employees' entries until they are put under a Team Lead.</p>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
        {people.map((p) => (
          <label key={p.id} className="flex items-center gap-2 text-sm text-gray-800">
            <input type="checkbox" checked={picked.has(p.id)} onChange={() => toggle(p.id)} className="h-4 w-4 rounded border-surface-border text-brand-500" />
            {p.name} <span className="text-xs text-gray-500">{p.code}</span>
          </label>
        ))}
      </div>
      {platform.team_leads.length === 0 ? (
        <p className="mt-3 text-xs text-gray-600">There is no {platform.name} Team Lead yet. Open a person under Users &amp; access and set their entry role to Team Lead first.</p>
      ) : (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <div className="w-64"><Select label="Team Lead" value={lead} onChange={(e) => setLead(e.target.value)} options={platform.team_leads.map((t) => ({ value: t.id, label: `${t.name} (${t.code})` }))} /></div>
          <Button isLoading={assign.isPending} disabled={!lead} onClick={() => assign.mutate(ids)}>
            {picked.size ? `Put ${picked.size} selected under this Team Lead` : `Put all ${people.length} under this Team Lead`}
          </Button>
        </div>
      )}
    </div>
  );
}

/** Administrators and developers: who reports to whom, per platform: administrators, then Reviewers, then each Team Lead with their employees. */
export function HierarchyPanel() {
  const q = useQuery({ queryKey: ["entry-hierarchy"], queryFn: () => apiRequest<Hierarchy>("/entries/hierarchy", { silent: true }), gcTime: 0, staleTime: 0 });
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.isError || !q.data) return <ErrorState message={q.error instanceof Error ? q.error.message : "Couldn't load the hierarchy."} onRetry={() => q.refetch()} />;
  const h = q.data;
  const open = h.platforms.reduce((n, p) => n + p.unassigned.length, 0);

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-gray-500">
        Administrators see everything. On each platform a Reviewer checks what the Team Leads have verified, and each Team Lead verifies the entries of the employees under them.
        {open > 0 ? <b className="text-status-warning"> {open} employee{open === 1 ? " has" : "s have"} no Team Lead yet.</b> : " Every employee has a Team Lead."}
      </p>
      <div className="rounded-2xl border border-surface-border bg-surface p-4 shadow-card sm:p-5">
        <Level label="Administrators" tone="bg-ink-950 text-white">{names(h.admins) ?? "—"}</Level>
        {h.reviewers_all_platforms.length > 0 && <div className="mt-2"><Level label="Reviewers, all platforms" tone="bg-emerald-500/15 text-emerald-700">{names(h.reviewers_all_platforms)}</Level></div>}
      </div>

      {h.platforms.map((p) => (
        <section key={p.id} className="flex flex-col gap-4 rounded-2xl border border-surface-border bg-surface p-4 shadow-card sm:p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-lg font-extrabold text-heading">{p.name}</h3>
            <span className="text-xs text-gray-500">{p.employees} employee{p.employees === 1 ? "" : "s"} · {p.team_leads.length} Team Lead{p.team_leads.length === 1 ? "" : "s"}</span>
          </div>
          <Level label="Reviewers" tone="bg-emerald-500/15 text-emerald-700">
            {names(p.reviewers) ?? (h.reviewers_all_platforms.length ? "covered by the all-platform Reviewers above" : <span className="text-status-warning">none yet: entries stop at the Team Lead</span>)}
          </Level>
          <div className="grid gap-3 md:grid-cols-2">
            {p.team_leads.map((t) => (
              <div key={t.id} className="rounded-xl border border-surface-border bg-surface-subtle/50 p-3.5">
                <p className="text-sm font-bold text-heading">{t.name} <span className="text-xs font-medium text-gray-500">{t.code} · Team Lead</span></p>
                <p className="mt-0.5 text-xs text-gray-500">{t.employees.length} employee{t.employees.length === 1 ? "" : "s"}</p>
                <p className="mt-1.5 text-sm text-gray-700">{t.employees.length ? t.employees.map((e) => e.name).join(", ") : <span className="text-status-warning">nobody reports to this Team Lead yet</span>}</p>
              </div>
            ))}
          </div>
          <Unassigned platform={p} />
          {p.under_other_platform_lead.length > 0 && (
            <p className="rounded-xl bg-surface-subtle px-3.5 py-3 text-xs text-gray-600">
              <b>{p.under_other_platform_lead.length}</b> report to a Team Lead of another platform: {p.under_other_platform_lead.map((e) => `${e.name} → ${e.team_lead.name}`).join(", ")}. Move them from the person's entry role.
            </p>
          )}
        </section>
      ))}
    </div>
  );
}
