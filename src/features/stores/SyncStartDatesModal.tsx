import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { useStoreMutations, usePartners } from "@/features/stores/useStores";

/** Sets every store's start date to the first day it was supplied, read from the order sheet. Preview first. */
export function SyncStartDatesModal({ onClose }: { onClose: () => void }) {
  const { data: partners = [] } = usePartners();
  const { startDates } = useStoreMutations();
  const [platform, setPlatform] = useState("");
  const [replace, setReplace] = useState(false);

  const preview = startDates.data?.dryRun ? startDates.data : null;
  const done = startDates.data && !startDates.data.dryRun ? startDates.data : null;
  const run = (dryRun: boolean) => startDates.mutate({ platform, replaceExisting: replace, dryRun });

  return (
    <Modal
      open
      onClose={onClose}
      title="Sync store start dates"
      description="A store's start date is the first day it was supplied: the earliest day with bottles in the order sheet."
      footer={
        done ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="secondary" onClick={() => run(true)} isLoading={startDates.isPending && !preview}>
              Preview
            </Button>
            <Button onClick={() => run(false)} disabled={!preview || preview.toChange === 0} isLoading={startDates.isPending && !!preview}>
              Update {preview?.toChange ?? 0} stores
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <Select
          label="Platform"
          value={platform}
          onChange={(e) => { setPlatform(e.target.value); startDates.reset(); }}
          placeholder="All platforms"
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
        />
        <label className="flex cursor-pointer items-start gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4"
            checked={replace}
            onChange={(e) => { setReplace(e.target.checked); startDates.reset(); }}
          />
          <span>
            Also replace start dates that are already set
            <span className="block text-xs text-gray-500">Off: only stores with an empty start date are filled; dates entered by hand are kept.</span>
          </span>
        </label>
        {preview && (
          <div className="rounded-lg bg-surface-subtle px-3 py-2.5 text-sm text-gray-700">
            <p>
              <b>{preview.toFill}</b> store{preview.toFill === 1 ? "" : "s"} with an empty start date will be filled.
            </p>
            <p className="mt-1">
              <b>{preview.differs}</b> already {preview.differs === 1 ? "has" : "have"} a different date
              {preview.replaceExisting ? " and will be replaced." : " and will be left as they are."}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              {preview.unchanged} already match · {preview.noOrders} have no supplied day in the order sheet yet (left empty) · {preview.stores} stores checked.
            </p>
          </div>
        )}
        {done && (
          <p className="rounded-lg bg-status-success-soft px-3 py-2 text-sm text-status-success">
            Updated the start date of {done.toChange} store{done.toChange === 1 ? "" : "s"}. Pending days and the monthly store lists use the new dates.
          </p>
        )}
        {startDates.error && (
          <p role="alert" className="text-sm text-status-danger">
            {startDates.error instanceof Error ? startDates.error.message : "Could not sync the start dates."}
          </p>
        )}
      </div>
    </Modal>
  );
}
