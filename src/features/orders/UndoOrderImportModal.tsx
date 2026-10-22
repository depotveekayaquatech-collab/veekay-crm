import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { usePartners } from "@/features/stores/useStores";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";

interface Run {
  run_id: string;
  at: string;
  by: string;
  source: string | null;
  created_in_month: number;
  can_delete: number;
  changed_since: number;
  overwrote_in_month: number;
  first_day: string | null;
  last_day: string | null;
}

interface Preview {
  will_delete: number;
  will_restore: number;
  kept_untouched_by_us: number;
  dry_run: boolean;
  deleted?: number;
  restored?: number;
}

const thisMonth = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`;
};
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/**
 * Developer: put ONE month back the way it was before chosen order imports. What an import created that month is deleted (the database keeps a
 * copy of every deleted row), numbers it overwrote are restored, and anything changed since by someone else is left alone. Other months stay.
 */
export function UndoOrderImportModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { data: partners = [] } = usePartners();
  const [platform, setPlatform] = useState("");
  const slug = platform || partners[0]?.slug || "";
  const [month, setMonth] = useState(thisMonth());
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState("");

  const runs = useQuery({
    queryKey: ["order-import-runs", slug, month],
    queryFn: () => apiRequest<{ runs: Run[] }>(`/orders/import-runs?platform=${encodeURIComponent(slug)}&month=${month}`),
    enabled: !!slug && /^\d{4}-\d{2}$/.test(month),
    gcTime: 0,
  });

  const ids = [...picked];
  const run = useMutation({
    mutationFn: (dry: boolean) =>
      apiRequest<Preview>("/orders/import-revert", {
        method: "POST",
        body: { platform: slug, month, run_ids: ids, dry_run: dry, confirm },
      }),
    onSuccess: (r) => {
      if (r.dry_run) return;
      for (const k of ["calendar", "daily-overview", "order-insights", "report", "pending", "my-stores", "capping", "order-import-runs"]) qc.invalidateQueries({ queryKey: [k] });
      pushToast(`${r.deleted ?? 0} entries removed, ${r.restored ?? 0} restored.`, "success");
    },
  });
  const preview = run.data?.dry_run ? run.data : null;
  const done = run.data && !run.data.dry_run ? run.data : null;
  const expected = `REVERT ${slug.toUpperCase()} ${month}`;
  const reset = () => run.reset();

  const toggle = (id: string) => {
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
    reset();
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title="Undo an order import for one month"
      description="Removes what the chosen import wrote into this month and puts back numbers it overwrote. Other months and anything edited since are left alone."
      footer={
        done ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="secondary" onClick={() => run.mutate(true)} disabled={ids.length === 0} isLoading={run.isPending && !preview}>
              Preview
            </Button>
            <Button
              variant="danger"
              onClick={() => run.mutate(false)}
              disabled={!preview || (preview.will_delete + preview.will_restore === 0) || confirm.trim().toUpperCase() !== expected}
              isLoading={run.isPending && !!preview}
            >
              Undo {preview ? preview.will_delete + preview.will_restore : 0} entries
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Select label="Platform" value={slug} onChange={(e) => { setPlatform(e.target.value); setPicked(new Set()); reset(); }} options={partners.map((p) => ({ value: p.slug, label: p.name }))} />
          <Input label="Month" type="month" value={month} onChange={(e) => { setMonth(e.target.value); setPicked(new Set()); reset(); }} />
        </div>

        {runs.isLoading ? (
          <p className="text-sm text-gray-500">Looking for imports…</p>
        ) : (runs.data?.runs ?? []).length === 0 ? (
          <p className="rounded-lg bg-surface-subtle px-3 py-2 text-sm text-gray-600">No order import left entries in {month} on this platform.</p>
        ) : (
          <ul className="max-h-64 divide-y divide-surface-border overflow-auto rounded-lg border border-surface-border text-sm">
            {runs.data!.runs.map((r) => (
              <li key={r.run_id}>
                <label className="flex cursor-pointer items-start gap-3 px-3 py-2.5">
                  <input type="checkbox" className="mt-1" checked={picked.has(r.run_id)} onChange={() => toggle(r.run_id)} />
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium text-gray-900">{when(r.at)} · by {r.by}{r.source ? ` · ${r.source}` : ""}</span>
                    <span className="block text-xs text-gray-500">
                      wrote <b>{r.created_in_month}</b> entries in {month}
                      {r.first_day ? ` (days ${r.first_day.slice(8)}–${r.last_day?.slice(8)})` : ""}
                      {r.overwrote_in_month ? <>, overwrote <b>{r.overwrote_in_month}</b> existing number{r.overwrote_in_month === 1 ? "" : "s"}</> : null}
                      {r.changed_since ? `; ${r.changed_since} were edited since and will stay` : ""}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}

        {preview && (
          <div className="rounded-lg bg-surface-subtle px-3 py-2 text-sm text-gray-700">
            <p>
              <b>{preview.will_delete}</b> entries will be removed and <b>{preview.will_restore}</b> numbers put back to what employees had entered
              {preview.kept_untouched_by_us ? `; ${preview.kept_untouched_by_us} entries edited since stay as they are` : ""}. Removed entries are kept in the
              database's deleted-rows archive and can be restored from Entries audit.
            </p>
            <div className="mt-3">
              <Input label={`Type  ${expected}  to confirm`} value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
            </div>
          </div>
        )}
        {done && (
          <p className="rounded-lg bg-status-success-soft px-3 py-2 text-sm text-status-success">
            Done: {done.deleted ?? 0} entries removed and {done.restored ?? 0} numbers restored for {month}.
          </p>
        )}
        {run.error && (
          <p role="alert" className="text-sm text-status-danger">{run.error instanceof Error ? run.error.message : "Could not undo the import."}</p>
        )}
      </div>
    </Modal>
  );
}
