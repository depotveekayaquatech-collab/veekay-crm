import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { usePartners } from "@/features/stores/useStores";
import { mergeStores, mergeSuggestions, type MergePairInput } from "@/services/stores";
import { pushToast } from "@/lib/toast";

/** "OLD NEW" per line (space, comma or tab between the two IDs). */
function parsePairs(text: string): { oldCode: string; newCode: string }[] {
  return text
    .split(/\r?\n/)
    .map((l) => (l.includes("\t") ? l.split("\t").map((x) => x.trim()) : l.trim().split(/[\s,;]+/)).filter(Boolean))
    .filter((p) => p.length >= 2)
    .map((p) => ({ oldCode: p[0], newCode: p[1] }));
}

const movedText = (m: Record<string, number>) =>
  Object.entries(m)
    .map(([k, v]) => `${v} ${k}`)
    .join(", ");

/**
 * Stores that already exist twice: once under a temporary Outlet ID and once under the real one (uploaded in a later sheet).
 * This moves the temporary store's orders, documents, tickets, cash purchases and vendor history onto the real one and removes
 * the temporary one. A preview comes first; a pair that would overwrite anything is refused and left untouched.
 */
export function MergeStoresModal({ onClose, initial }: { onClose: () => void; initial?: { platform: string; pairs: MergePairInput[] } }) {
  const qc = useQueryClient();
  const { data: partners = [] } = usePartners();
  const [platform, setPlatform] = useState(initial?.platform ?? "");
  const slug = platform || partners[0]?.slug || "";
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [manual, setManual] = useState("");
  const fixed = initial?.pairs ?? [];              // exact pairs chosen on the Duplicates page (by store id)

  const found = useQuery({ queryKey: ["merge-suggestions", slug], queryFn: () => mergeSuggestions(slug), enabled: !!slug });
  const suggestions = found.data ?? [];
  useEffect(() => setSkipped(new Set()), [slug]);

  const pairs = useMemo(
    () => [
      ...fixed,
      ...(initial ? [] : suggestions.filter((s) => !skipped.has(s.oldCode)).map((s) => ({ oldCode: s.oldCode, newCode: s.newCode }))),
      ...parsePairs(manual),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [suggestions, skipped, manual],
  );

  const run = useMutation({
    mutationFn: (dryRun: boolean) => mergeStores(slug, pairs, dryRun),
    onSuccess: (r) => {
      if (r.dryRun) return;
      for (const k of ["stores", "duplicate-stores", "merge-suggestions", "inventory", "pending", "order-insights", "matrix"]) qc.invalidateQueries({ queryKey: [k] });
      pushToast(`${r.merged} store${r.merged === 1 ? "" : "s"} merged.`, "success");
    },
  });
  const shown = run.data;
  const preview = shown?.dryRun ? shown : null;
  const done = shown && !shown.dryRun ? shown : null;

  const toggle = (code: string) => {
    setSkipped((s) => {
      const n = new Set(s);
      if (n.has(code)) n.delete(code);
      else n.add(code);
      return n;
    });
    run.reset();
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title="Merge duplicate stores"
      description="For stores that now exist twice: everything on the temporary store moves to the one with the real Outlet ID, then the temporary store is removed."
      footer={
        done ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="secondary" onClick={() => run.mutate(true)} disabled={!slug || pairs.length === 0} isLoading={run.isPending && !preview}>
              Preview {pairs.length} pair{pairs.length === 1 ? "" : "s"}
            </Button>
            <Button variant="danger" onClick={() => run.mutate(false)} disabled={!preview || preview.merged === 0} isLoading={run.isPending && !!preview}>
              Merge {preview?.merged ?? 0} store{preview?.merged === 1 ? "" : "s"}
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <Select
          label="Platform"
          value={slug}
          onChange={(e) => { setPlatform(e.target.value); run.reset(); }}
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
          disabled={!!initial}
        />

        {initial ? (
          <ul className="divide-y divide-surface-border rounded-lg border border-surface-border text-sm">
            {fixed.map((f) => (
              <li key={`${f.oldId}-${f.newId}`} className="px-3 py-2 text-gray-700">
                Move everything from <b>{f.oldCode}</b> into <b>{f.newCode}</b>, then remove <b>{f.oldCode}</b>.
              </li>
            ))}
          </ul>
        ) : (
        <>
        <div>
          <p className="text-sm font-semibold text-gray-800">Found automatically (same store name under two Outlet IDs)</p>
          {found.isLoading ? (
            <p className="mt-1 text-sm text-gray-500">Looking…</p>
          ) : suggestions.length === 0 ? (
            <p className="mt-1 text-sm text-gray-500">None found. You can type pairs below.</p>
          ) : (
            <ul className="mt-2 max-h-56 divide-y divide-surface-border overflow-auto rounded-lg border border-surface-border text-sm">
              {suggestions.map((s) => (
                <li key={s.oldCode}>
                  <label className="flex cursor-pointer items-start gap-3 px-3 py-2">
                    <input type="checkbox" className="mt-1" checked={!skipped.has(s.oldCode)} onChange={() => toggle(s.oldCode)} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-gray-900">{s.name}</span>
                      <span className="block text-xs text-gray-500">
                        {s.oldCode} ({s.oldOrderDays} order days) → <b>{s.newCode}</b> ({s.newOrderDays} order days)
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-semibold text-gray-800">Other pairs (optional): one per line, old Outlet ID then new Outlet ID</span>
          <textarea
            value={manual}
            onChange={(e) => { setManual(e.target.value); run.reset(); }}
            rows={3}
            placeholder={"TEMP-001 BL-48213\nTEMP-002 BL-48977"}
            className="rounded-lg border border-surface-border bg-surface px-3 py-2 font-mono text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </label>
        </>
        )}

        {shown && (
          <div className="rounded-lg bg-surface-subtle px-3 py-2 text-sm text-gray-700">
            <p className="font-semibold">
              {done ? `Merged ${shown.merged}` : `${shown.merged} can be merged`}
              {shown.skipped > 0 ? `, ${shown.skipped} skipped` : ""}.
            </p>
            <ul className="mt-2 max-h-56 space-y-1 overflow-auto">
              {shown.results.map((r) => (
                <li key={`${r.oldCode}-${r.newCode}`} className={r.ok ? "text-gray-700" : "text-status-danger"}>
                  {r.oldCode} → {r.newCode}
                  {r.name ? ` (${r.name})` : ""}: {r.ok ? movedText(r.moved) || "nothing to move" : r.reason}
                </li>
              ))}
            </ul>
          </div>
        )}
        {run.error && (
          <p role="alert" className="text-sm text-status-danger">
            {run.error instanceof Error ? run.error.message : "Could not merge the stores."}
          </p>
        )}
      </div>
    </Modal>
  );
}
