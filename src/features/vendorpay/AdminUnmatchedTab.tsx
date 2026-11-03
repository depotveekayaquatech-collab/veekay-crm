import { useState } from "react";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Table, Td, Th } from "@/components/ui/Table";
import { EMPTY_VENDOR, useResolveMutations, useUnmatched, type UnmatchedGroup, type VendorForm } from "@/features/vendorpay/adminApi";
import { useVendorChoices } from "@/features/vendorpay/api";
import { vendorLabel } from "@/features/vendorpay/format";
import { Amount } from "@/features/vendorpay/parts";
import { VendorFormModal } from "@/features/vendorpay/VendorFormModal";

type Action = { kind: "create" | "map"; group: UnmatchedGroup };

function MapModal({ group, isSaving, onClose, onPick }: { group: UnmatchedGroup; isSaving: boolean; onClose: () => void; onPick: (code: string) => void }) {
  const { data: vendors = [] } = useVendorChoices();
  const [target, setTarget] = useState("");
  return (
    <Modal
      open
      onClose={onClose}
      title={`Map ${group.vendorCode ?? group.accountName} to an existing vendor`}
      description={group.vendorCode ? "Its entries move to that vendor, and Busy sending this code again will land there too." : "Its entries move to that vendor. They have no code, so this is a one-time move."}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button isLoading={isSaving} disabled={!target} onClick={() => onPick(target)}>Map and move entries</Button>
        </>
      }
    >
      <Select label="Vendor" value={target} searchable placeholder="Choose a vendor" options={vendors.map((v) => ({ value: v.vendorCode, label: vendorLabel(v) }))} onChange={(e) => setTarget(e.target.value)} />
    </Modal>
  );
}

export function AdminUnmatchedTab() {
  const { data, isLoading, isError, refetch } = useUnmatched();
  const { createVendor, mapToVendor } = useResolveMutations();
  const [action, setAction] = useState<Action | null>(null);

  async function run(work: () => Promise<unknown>) {
    try {
      await work();
      setAction(null);
    } catch {
      /* the API layer already showed the reason */
    }
  }

  if (isError) return <ErrorState message="Couldn't load the unmatched entries." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <Skeleton className="h-48 w-full" />;
  if (data.length === 0) return <EmptyState title="Nothing unmatched" description="Every entry from Busy belongs to a vendor here. Rows with an unknown vendor code would be listed here, never dropped." />;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-gray-600">These entries came from Busy with a vendor code that is not a vendor here. They are kept until you add the vendor or map the code to one you already have.</p>
      <Table>
        <thead>
          <tr>
            <Th>Code from Busy</Th>
            <Th>Account name</Th>
            <Th className="text-right">Entries</Th>
            <Th className="text-right">Bills</Th>
            <Th className="text-right">Payments</Th>
            <Th>Dates</Th>
            <Th className="text-right">Resolve</Th>
          </tr>
        </thead>
        <tbody>
          {data.map((g) => (
            <tr key={`${g.vendorCode ?? ""}|${g.accountName}`}>
              <Td className="tabular-nums font-semibold text-heading">{g.vendorCode ?? "No code found"}</Td>
              <Td>{g.accountName}</Td>
              <Td className="text-right tabular-nums">{g.rows}</Td>
              <Td className="text-right"><Amount value={g.bills} /></Td>
              <Td className="text-right"><Amount value={g.payments} /></Td>
              <Td className="whitespace-nowrap text-xs">{g.firstDate} to {g.lastDate}</Td>
              <Td className="text-right">
                <div className="flex justify-end gap-2">
                  <Button size="sm" onClick={() => setAction({ kind: "create", group: g })}>Create vendor</Button>
                  <Button size="sm" variant="secondary" onClick={() => setAction({ kind: "map", group: g })}>Map to existing</Button>
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>

      {action?.kind === "create" && (
        <VendorFormModal
          key={`${action.group.vendorCode}|${action.group.accountName}`}
          title="Create vendor from these entries"
          description="The vendor is added and all its waiting entries move into its ledger."
          initial={{ ...EMPTY_VENDOR, vendorCode: action.group.vendorCode ?? "", name: action.group.suggestedName }}
          codeLocked={Boolean(action.group.vendorCode)}
          isSaving={createVendor.isPending}
          onClose={() => setAction(null)}
          onSubmit={(vendor: VendorForm) => void run(() => createVendor.mutateAsync({ group: action.group, vendor }))}
        />
      )}
      {action?.kind === "map" && (
        <MapModal group={action.group} isSaving={mapToVendor.isPending} onClose={() => setAction(null)} onPick={(target) => void run(() => mapToVendor.mutateAsync({ group: action.group, target }))} />
      )}
    </div>
  );
}
