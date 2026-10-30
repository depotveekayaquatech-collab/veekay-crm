import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { STATUS, platformTone } from "@/features/stores/storeDisplay";
import type { Store } from "@/types/store";

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <p className="text-[13px] leading-snug text-gray-700">
      <span className="font-semibold text-gray-900">{label}:</span> {children}
    </p>
  );
}

export function StoreCard({
  store, canManage, onView, onEdit, onClose,
}: {
  store: Store;
  canManage: boolean;
  onView: () => void;
  onEdit: () => void;
  onClose: () => void;
}) {
  const s = STATUS[store.status];
  const place = [store.city, store.state].filter(Boolean).join(", ");
  return (
    <article className="flex flex-col gap-3 rounded-2xl border border-surface-border bg-surface p-4 shadow-card transition-shadow hover:shadow-md">
      <header className="flex items-start justify-between gap-3">
        <h3 className="text-[15px] font-bold leading-snug text-heading">{store.name}</h3>
        <Badge dot tone={s.tone}>{s.label}</Badge>
      </header>
      <div>
        <Badge tone={platformTone(store.partnerSlug)}>{(store.partnerName ?? "").toUpperCase()}</Badge>
      </div>

      <div className="flex flex-col gap-1">
        <Line label="Store ID">{store.externalCode}</Line>
        {store.crmCode ? <Line label="CRM code">{store.crmCode}</Line> : null}
        {(store.regionName || store.entity) && (
          <Line label="Region">
            {store.regionName ?? "—"}
            {store.entity ? <> <span className="font-semibold text-gray-900">Entity:</span> {store.entity}</> : null}
          </Line>
        )}
        <Line label="Location">{place || "—"}</Line>
        <Line label="Address"><span className="text-gray-600">{store.address ?? "—"}</span></Line>
      </div>

      <div className="flex flex-col gap-1 border-t border-surface-border pt-3">
        <Line label="Vendor">
          {store.vendorName ? (
            <>
              <span className="font-semibold text-brand-700">{store.vendorName}</span>
              {store.vendorNumber ? <span className="text-gray-500"> ({store.vendorNumber})</span> : null}
            </>
          ) : (
            <span className="text-gray-400">Not assigned</span>
          )}
        </Line>
        <Line label="POC">
          {store.pocName ? (
            <>
              {store.pocName}
              {store.pocNumber ? <span className="text-gray-500"> · {store.pocNumber}</span> : null}
            </>
          ) : (
            <span className="text-gray-400">Not assigned</span>
          )}
        </Line>
      </div>

      <footer className="mt-auto flex flex-wrap gap-2 pt-1">
        <Button size="sm" variant="secondary" onClick={onView} className="flex-1">View details</Button>
        {canManage && <Button size="sm" variant="secondary" onClick={onEdit} className="flex-1">Edit info</Button>}
        {canManage && store.status !== "CLOSE" && (
          <Button size="sm" variant="ghost" onClick={onClose} className="text-status-danger hover:bg-status-danger-soft hover:text-status-danger">Close</Button>
        )}
      </footer>
    </article>
  );
}
