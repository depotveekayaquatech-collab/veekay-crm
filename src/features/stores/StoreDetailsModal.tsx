import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { VendorHistory } from "@/features/stores/VendorHistory";
import type { Store } from "@/types/store";

const STATUS_LABEL = { LIVE: "Live", PENDING: "Pending", CLOSE: "Closed" } as const;

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] font-bold text-gray-500">{label}</dt>
      <dd className="text-sm text-gray-900">{value || <span className="text-gray-400">—</span>}</dd>
    </div>
  );
}

export function StoreDetailsModal({ store, onClose, onEdit }: { store: Store; onClose: () => void; onEdit?: () => void }) {
  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={store.name}
      description={`${store.partnerName ?? ""} · Store ID ${store.externalCode}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Close</Button>
          {onEdit && <Button onClick={onEdit}>Edit info</Button>}
        </>
      }
    >
      <dl className="grid gap-4 sm:grid-cols-2">
        <Row label="Status" value={<Badge dot tone={store.status === "LIVE" ? "success" : store.status === "PENDING" ? "warning" : "neutral"}>{STATUS_LABEL[store.status]}</Badge>} />
        <Row label="Start date" value={store.startDate} />
        <Row label="Platform" value={store.partnerName} />
        <Row label="Region" value={store.regionName} />
        <Row label="Entity" value={store.entity} />
        <Row label="State" value={store.state} />
        <Row label="City" value={store.city} />
        <div className="sm:col-span-2"><Row label="Address" value={store.address} /></div>
        <Row label="Vendor" value={store.vendorName ? `${store.vendorName}${store.vendorNumber ? ` (${store.vendorNumber})` : ""}` : null} />
        <Row label="POC" value={store.pocName ? `${store.pocName}${store.pocNumber ? ` · ${store.pocNumber}` : ""}` : null} />
        <VendorHistory storeId={store.id} minEntries={1} />
      </dl>
    </Modal>
  );
}
