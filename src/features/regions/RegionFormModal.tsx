import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { useRegionMutations } from "@/features/regions/useRegions";
import type { Region } from "@/types/region";

interface Props {
  onClose: () => void;
  region?: Region | null;
}

/** Mounted fresh each time it opens (parent keys/guards it), so form state
 * initializes from props without a sync effect. */
export function RegionFormModal({ onClose, region }: Props) {
  const { create, update } = useRegionMutations();
  const editing = Boolean(region);
  const [name, setName] = useState(region?.name ?? "");
  const [code, setCode] = useState(region?.code ?? "");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (region) {
        await update.mutateAsync({ id: region.id, input: { name, code } });
      } else {
        await create.mutateAsync({ name, code });
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  const busy = create.isPending || update.isPending;

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? "Edit region" : "New region"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="region-form" isLoading={busy}>
            {editing ? "Save changes" : "Create region"}
          </Button>
        </>
      }
    >
      <form id="region-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        <Input
          label="Code"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          hint="Short unique identifier, e.g. DEL-NCR"
          required
        />
        {error && <p className="text-sm text-status-danger">{error}</p>}
      </form>
    </Modal>
  );
}
