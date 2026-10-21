import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useStoreMutations, usePartners } from "@/features/stores/useStores";

/** Sets every store's start date to the first day it was supplied, read from the order sheet. Preview first. */
export function SyncStartDatesModal({ onClose }: { onClose: () => void }) {
  const { data: partners = [] } = usePartners();
  const { startDates } = useStoreMutations();
  const [platform, setPlatform] = useState("");
  const [replace, setReplace] = useState(false);
  const [vendor, setVendor] = useState("");

  const preview = startDates.data?.dryRun ? startDates.data : null;
  const done = startDates.data && !startDates.data.dryRun ? startDates.data : null;
  const run = (dryRun: boolean, p = platform, r = replace, v = vendor) => startDates.mutate({ platform: p, replaceExisting: r, dryRun, vendor: v });

  // Show what would change as soon as the window opens, and again whenever an option changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { run(true); }, []);

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
            <Button onClick={() => run(false)} disabled={!preview || preview.toChange === 0 || startDates.isPending} isLoading={startDates.isPending && !startDates.variables?.dryRun}>
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
          onChange={(e) => { setPlatform(e.target.value); run(true, e.target.value); }}
          placeholder="All platforms"
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
        />
        <Input
          label="Vendor (optional)"
          value={vendor}
          onChange={(e) => setVendor(e.target.value)}
          onBlur={() => run(true)}
          onKeyDown={(e) => e.key === "Enter" && run(true)}
          placeholder="e.g. RAJ GGN — blank = every vendor"
          hint="Only this vendor's stores are checked and changed."
        />
        <label className="flex cursor-pointer items-start gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4"
            checked={replace}
            onChange={(e) => { setReplace(e.target.checked); run(true, platform, e.target.checked); }}
          />
          <span>
            Also replace start dates that are earlier than the first supply
            <span className="block text-xs text-gray-500">
              Off: dates are filled or moved back to the first supply, but a date you typed that is earlier than our first order is kept
              (the store may have started before the order sheets begin).
            </span>
          </span>
        </label>
        {startDates.isPending && startDates.variables?.dryRun && <p role="status" className="text-sm text-gray-500">Checking the order sheet…</p>}
        {preview && !startDates.isPending && (
          <div className="rounded-lg bg-surface-subtle px-3 py-2.5 text-sm text-gray-700">
            <p>
              <b>{preview.toFill}</b> store{preview.toFill === 1 ? "" : "s"} with an empty start date will be filled.
            </p>
            <p className="mt-1">
              <b>{preview.moveEarlier}</b> {preview.moveEarlier === 1 ? "has" : "have"} a date later than the first supply and will move back to it.
            </p>
            <p className="mt-1">
              <b>{preview.keepHandDates}</b> {preview.keepHandDates === 1 ? "has" : "have"} a date earlier than the first supply in the order sheet
              {preview.replaceExisting ? " and will be replaced with it." : " and will be kept as they are."}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              {preview.unchanged} already match · {preview.noOrders} have no supplied day in the order sheet yet (left empty) · {preview.stores} stores checked.
            </p>
            {preview.noOrders > 0 && (
              <details className="mt-2 text-xs text-gray-600">
                <summary className="cursor-pointer font-semibold">
                  Which stores have no supplied day?{" "}
                  {Object.entries(preview.noOrdersByStatus).map(([s, n]) => `${s.toLowerCase()} ${n}`).join(" · ")}
                </summary>
                <p className="mt-1">
                  Pending and closed stores normally have no orders. A <b>live</b> store here means no bottles are recorded for it in the order sheet
                  (check its Outlet ID matches the order sheet).
                </p>
                {preview.noOrdersLiveSample.length > 0 && (
                  <ul className="mt-1 max-h-32 list-disc overflow-auto pl-4">
                    {preview.noOrdersLiveSample.map((s) => <li key={`${s.platform}-${s.code}`}>{s.name} <span className="text-gray-400">({s.platform} · {s.code})</span></li>)}
                  </ul>
                )}
              </details>
            )}
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
