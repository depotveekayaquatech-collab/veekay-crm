import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useStoreMutations, usePartners } from "@/features/stores/useStores";

/** Removes every store of one platform (or all) with its order history, so a wrong import can be redone. */
export function DeleteAllStoresModal({ onClose }: { onClose: () => void }) {
  const { data: partners = [] } = usePartners();
  const { removeAll } = useStoreMutations();
  const [platform, setPlatform] = useState("");
  const [typed, setTyped] = useState("");

  const chosen = platform || partners[0]?.slug || "";
  const name = partners.find((p) => p.slug === chosen)?.name ?? "";
  const phrase = chosen ? `DELETE ${chosen.toUpperCase()}` : "";
  const ok = !!phrase && typed.trim().toUpperCase() === phrase;

  return (
    <Modal
      open
      onClose={onClose}
      title="Remove all stores"
      description="Use this to clear a wrongly imported list, then import the correct one."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            variant="danger"
            disabled={!ok}
            isLoading={removeAll.isPending}
            onClick={() => removeAll.mutate({ platform: chosen, confirm: typed.trim() }, { onSuccess: onClose })}
          >
            Remove all {name} stores
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Select
          label="Platform"
          value={chosen}
          onChange={(e) => {
            setPlatform(e.target.value);
            setTyped("");
          }}
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
        />
        <p className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">
          This deletes <b>every {name} store</b> with its compliance documents, tickets and partner logins. Order history is
          archived first and comes back automatically when a store with the same platform and Outlet ID is added or
          imported again. Other platforms are not touched.
        </p>
        <Input label={`Type ${phrase} to confirm`} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        {removeAll.error && (
          <p role="alert" className="text-sm text-status-danger">
            {removeAll.error instanceof Error ? removeAll.error.message : "Could not remove the stores."}
          </p>
        )}
      </div>
    </Modal>
  );
}
