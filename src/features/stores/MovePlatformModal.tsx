import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useStoreMutations, usePartners } from "@/features/stores/useStores";

/** Re-files stores that were imported under the wrong platform; order history moves with each store. */
export function MovePlatformModal({ onClose }: { onClose: () => void }) {
  const { data: partners = [] } = usePartners();
  const { move } = useStoreMutations();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [contains, setContains] = useState("");

  const src = from || partners[0]?.slug || "";
  const dst = to || partners.find((p) => p.slug !== src)?.slug || "";
  const options = partners.map((p) => ({ value: p.slug, label: p.name }));
  const preview = move.data?.dryRun ? move.data : null;
  const done = move.data && !move.data.dryRun ? move.data : null;
  const run = (dryRun: boolean) => move.mutate({ from: src, to: dst, contains: contains.trim(), dryRun });

  return (
    <Modal
      open
      onClose={onClose}
      title="Fix wrong platform"
      description="Stores imported under the wrong platform can be moved without losing their order history."
      footer={
        done ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="secondary" onClick={() => run(true)} disabled={!src || !dst || src === dst} isLoading={move.isPending && !preview}>
              Preview
            </Button>
            <Button variant="danger" onClick={() => run(false)} disabled={!preview || preview.moved === 0} isLoading={move.isPending && !!preview}>
              Move {preview?.moved ?? 0} stores
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Select label="Currently under" value={src} onChange={(e) => { setFrom(e.target.value); move.reset(); }} options={options} />
          <Select label="Should be under" value={dst} onChange={(e) => { setTo(e.target.value); move.reset(); }} options={options} />
        </div>
        <Input
          label="Only stores whose name or Outlet ID contains (optional)"
          value={contains}
          onChange={(e) => { setContains(e.target.value); move.reset(); }}
          autoComplete="off"
        />
        {preview && (
          <p className="rounded-lg bg-surface-subtle px-3 py-2 text-sm text-gray-700">
            {preview.matched} stores match. <b>{preview.moved}</b> will move from {preview.from} to {preview.to}
            {preview.skippedDuplicates > 0 && ` (${preview.skippedDuplicates} skipped: that Outlet ID already exists on ${preview.to})`}.
          </p>
        )}
        {done && (
          <p className="rounded-lg bg-status-success-soft px-3 py-2 text-sm text-status-success">
            Moved {done.moved} stores from {done.from} to {done.to}. Their order history moved with them.
          </p>
        )}
        {move.error && (
          <p role="alert" className="text-sm text-status-danger">
            {move.error instanceof Error ? move.error.message : "Could not move the stores."}
          </p>
        )}
      </div>
    </Modal>
  );
}
