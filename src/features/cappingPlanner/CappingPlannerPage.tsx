import { useMemo, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Dropdown";
import { IconDownload } from "@/components/ui/icons";
import { istToday, monthName, recentMonths } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import { buildRequest, removePriorityLine, type PlannerForm } from "@/features/cappingPlanner/helpers";
import { PlannerIssues } from "@/features/cappingPlanner/PlannerIssues";
import { PlannerTable } from "@/features/cappingPlanner/PlannerTable";
import { Feasibility, PlannerCards } from "@/features/cappingPlanner/PlannerSummary";
import { PriorityPanel } from "@/features/cappingPlanner/PriorityPanel";
import { useAuth } from "@/features/auth/useAuth";
import { pushToast } from "@/lib/toast";
import { downloadPlan, runPlan, type PlanRequest, type PlanResult, type PlannerMode, type PlannerProject } from "@/services/cappingPlanner";

const MODES: { id: PlannerMode; title: string; text: string }[] = [
  { id: "priority_first", title: "Priority First", text: "Your pasted priority stores first, in the order pasted, then the rest by remaining capacity." },
  { id: "max_capacity", title: "Maximum Capacity", text: "The stores with the most remaining capacity. The priority list does not change the ranking." },
];

function Label({ text, error, children }: { text: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
      {text}
      {children}
      {error && <span role="alert" className="text-xs font-medium text-status-danger">{error}</span>}
    </label>
  );
}

/**
 * Smart Capping Planner: capacity planning over the stores' monthly capping. Choose the number of stores, the target difference, the project, the month and the mode,
 * optionally paste priority stores, and press Calculate. The answer comes from the server in one call (not on every keystroke) and is a PLAN: it changes no entry,
 * and a proposed allocation is never supply.
 */
export function CappingPlannerPage() {
  const { user } = useAuth();
  const platform = user?.platformSlug?.toLowerCase();
  const thisMonth = istToday().slice(0, 7);
  const [form, setForm] = useState<PlannerForm>({ month: thisMonth, project: "zepto", mode: "priority_first", storeLimitText: "", targetText: "", priorityText: "" });
  const [ran, setRan] = useState<{ request: PlanRequest; result: PlanResult } | null>(null);
  const [exporting, setExporting] = useState(false);
  const set = (patch: Partial<PlannerForm>) => setForm((f) => ({ ...f, ...patch }));

  const built = useMemo(() => buildRequest(form), [form]);
  const calc = useMutation({ mutationFn: (req: PlanRequest) => runPlan(req), onSuccess: (result, request) => setRan({ request, result }) });
  const stale = ran !== null && JSON.stringify(ran.request) !== JSON.stringify(built.request);
  const totals = ran?.result.totals ?? null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (built.request && !calc.isPending) calc.mutate(built.request);
  }

  function removeEntry(position: number) {
    const priorityText = removePriorityLine(form.priorityText, position);
    set({ priorityText });
    const next = buildRequest({ ...form, priorityText }).request;
    if (next) calc.mutate(next);
  }

  async function exportXlsx() {
    if (!ran) return;
    setExporting(true);
    try {
      await downloadPlan(ran.request);
    } catch {
      /* the API layer already showed the reason */
    } finally {
      setExporting(false);
    }
    pushToast("Exported. The workbook is a plan, not supply.", "success");
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Smart Capping Planner"
        subtitle="Capacity planning over each store's monthly capping. A plan only: it changes no entry and a proposed allocation is never supply."
        action={<Button variant="secondary" onClick={() => void exportXlsx()} disabled={!ran} isLoading={exporting}><IconDownload className="h-4 w-4" /> Export Excel</Button>}
      />

      <PlannerCards totals={totals} />

      <form onSubmit={submit} className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-4 shadow-card" aria-label="Configuration">
        <h2 className="text-sm font-bold text-gray-900">Configuration</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Label text="Number of Stores to Use" error={built.errors.storeLimit}>
            <input className={field} inputMode="numeric" value={form.storeLimitText} onChange={(e) => set({ storeLimitText: e.target.value })} placeholder="Enter number of stores (e.g. 200)" aria-invalid={!!built.errors.storeLimit} />
          </Label>
          <Label text="Target Difference to Match" error={built.errors.target}>
            <input className={field} inputMode="numeric" value={form.targetText} onChange={(e) => set({ targetText: e.target.value })} placeholder="Enter required additional count (e.g. 50000)" aria-invalid={!!built.errors.target} />
          </Label>
          <Label text="Project">
            <SelectField className={field} value={form.project} onChange={(e) => set({ project: e.target.value as PlannerProject })}>
              <option value="zepto">Zepto</option>
              {!platform && <option value="blinkit">Blinkit</option>}
              {!platform && <option value="all">All Projects</option>}
            </SelectField>
          </Label>
          <Label text="Month">
            <SelectField className={field} value={form.month} onChange={(e) => set({ month: e.target.value })}>
              {recentMonths().map((m) => <option key={m} value={m}>{monthName(m)}{m === thisMonth ? " (this month)" : ""}</option>)}
            </SelectField>
          </Label>
        </div>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-[13px] font-semibold text-gray-700">Calculation mode</legend>
          <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Calculation mode">
            {MODES.map((m) => (
              <button key={m.id} type="button" role="radio" aria-checked={form.mode === m.id} onClick={() => set({ mode: m.id })}
                className={`rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${form.mode === m.id ? "border-brand-500 bg-brand-500/5 ring-1 ring-brand-500" : "border-surface-border hover:bg-surface-subtle"}`}>
                <span className="text-sm font-bold text-gray-900">{m.title}</span>
                <span className="mt-0.5 block text-xs text-gray-600">{m.text}</span>
              </button>
            ))}
          </div>
        </fieldset>

        {form.month !== thisMonth && <p className="text-xs text-gray-600">{monthName(form.month)} is finished: you will see its capacity and whether the target would fit, but no per-store allocation is proposed.</p>}
        <p className="text-xs text-gray-500">Leave the number of stores blank to use every eligible store. The monthly limit is the daily capping × 30; a store counts only with a valid capping.</p>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={!built.request} isLoading={calc.isPending}>Calculate</Button>
          {stale && !calc.isPending && <span className="text-xs font-medium text-status-warning">The inputs changed since the last calculation.</span>}
        </div>
      </form>

      <PriorityPanel text={form.priorityText} onText={(priorityText) => set({ priorityText })} entries={ran?.result.priority ?? null} stale={stale} onRemove={removeEntry} />

      {ran && totals && (
        <>
          <section role="note" className="rounded-xl border border-status-warning/50 bg-status-warning/5 p-3 text-xs text-gray-700">
            <b>{ran.result.note}</b> {ran.result.allocationNote ?? ""}
            {totals.priorityExceedsLimit && ` You pasted ${totals.priorityMatched} matched priority stores but the store limit is ${totals.storeLimit}, so only the first eligible ones that fit are considered; the rest are listed above with the reason.`}
          </section>
          <Feasibility totals={totals} />
          <PlannerTable rows={ran.result.rows} allocationAllowed={totals.allocationAllowed} />
          <PlannerIssues issues={ran.result.issues} />
        </>
      )}
    </div>
  );
}
