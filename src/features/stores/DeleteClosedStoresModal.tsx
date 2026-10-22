import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { deleteClosedStores } from "@/services/stores";
import { pushToast } from "@/lib/toast";

/**
 * Removes Closed stores that hold no history. A closed store with any order day, document, ticket or cash purchase is never
 * offered: closing keeps that history, and deleting would lose it. Tick off any store you want to keep.
 */
export function DeleteClosedStoresModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const found = useQuery({ queryKey: ["delete-closed-preview"], queryFn: () => deleteClosedStores({ dryRun: true }), gcTime: 0 });
  const [keep, setKeep] = useState<Set<string>>(new Set());
  useEffect(() => setKeep(new Set()), [found.data]);

  const run = useMutation({
    mutationFn: (ids: string[]) => deleteClosedStores({ storeIds: ids, dryRun: false }),
    onSuccess: (r) => {
      for (const k of ["stores", "duplicate-stores", "inventory", "pending", "order-insights", "matrix"]) qc.invalidateQueries({ queryKey: [k] });
      pushToast(`${r.deleted} closed store${r.deleted === 1 ? "" : "s"} deleted.`, "success");
    },
  });

  const d = found.data;
  const chosen = (d?.deletable ?? []).filter((s) => !keep.has(s.id));
  const done = run.data;

  const toggle = (id: string) =>
    setKeep((k) => {
      const n = new Set(k);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title="Delete closed stores"
      description="Only closed stores with no history are deleted. Any closed store that has orders, documents, tickets or cash purchases stays."
      footer={
        done ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              variant="danger"
              onClick={() => run.mutate(chosen.map((s) => s.id))}
              disabled={chosen.length === 0}
              isLoading={run.isPending}
            >
              Delete {chosen.length} store{chosen.length === 1 ? "" : "s"}
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        {found.isLoading && <p className="text-gray-500">Checking closed stores…</p>}
        {found.isError && <p role="alert" className="text-status-danger">Couldn't check the closed stores. Try again.</p>}
        {d && !done && (
          <>
            <p className="rounded-lg bg-surface-subtle px-3 py-2 text-gray-700">
              <b>{d.closed}</b> closed store{d.closed === 1 ? "" : "s"}: <b>{d.deletableCount}</b> can be deleted,{" "}
              <b>{d.keptWithOrders}</b> kept because they have order history
              {d.keptWithOtherRecords > 0 ? <>, <b>{d.keptWithOtherRecords}</b> kept because they have other records</> : null}.
            </p>
            {d.deletable.length === 0 ? (
              <p className="text-gray-500">There is nothing to delete.</p>
            ) : (
              <ul className="max-h-72 divide-y divide-surface-border overflow-auto rounded-lg border border-surface-border">
                {d.deletable.map((s) => (
                  <li key={s.id}>
                    <label className="flex cursor-pointer items-start gap-3 px-3 py-2">
                      <input type="checkbox" className="mt-1" checked={!keep.has(s.id)} onChange={() => toggle(s.id)} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium text-gray-900">{s.name}</span>
                        <span className="block text-xs text-gray-500">{s.platform} · {s.externalCode}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            {d.deletableCount > d.deletable.length && (
              <p className="text-xs text-gray-500">Showing the first {d.deletable.length}. Run it again after this to clear the rest.</p>
            )}
          </>
        )}
        {done && (
          <p className="rounded-lg bg-status-success-soft px-3 py-2 text-status-success">
            Deleted {done.deleted} closed store{done.deleted === 1 ? "" : "s"}. Stores with history were kept.
          </p>
        )}
        {run.error && (
          <p role="alert" className="text-status-danger">{run.error instanceof Error ? run.error.message : "Could not delete the stores."}</p>
        )}
      </div>
    </Modal>
  );
}
