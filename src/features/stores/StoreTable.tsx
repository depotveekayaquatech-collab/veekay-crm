import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Td, Th } from "@/components/ui/Table";
import { STATUS, platformTone } from "@/features/stores/storeDisplay";
import type { Store } from "@/types/store";

/**
 * The same stores as the cards, laid out to scan and compare: one row each, a header that stays in view while the rows scroll, and the same three actions
 * (view, edit, close) wired by the page exactly as for a card.
 */
export function StoreTable({
  stores, canManage, onView, onEdit, onClose,
}: {
  stores: Store[];
  canManage: boolean;
  onView: (s: Store) => void;
  onEdit: (s: Store) => void;
  onClose: (s: Store) => void;
}) {
  return (
    <div className="max-h-[calc(100vh-16rem)] overflow-auto rounded-xl border border-surface-border bg-surface">
      <table className="w-full min-w-[920px] border-collapse text-sm">
        <thead>
          <tr>
            <Th className="sticky top-0 z-10">Store</Th>
            <Th className="sticky top-0 z-10">Store ID</Th>
            <Th className="sticky top-0 z-10">Platform</Th>
            <Th className="sticky top-0 z-10">Region</Th>
            <Th className="sticky top-0 z-10">Location</Th>
            <Th className="sticky top-0 z-10">Vendor</Th>
            <Th className="sticky top-0 z-10">Status</Th>
            <Th className="sticky top-0 z-10 text-right">Actions</Th>
          </tr>
        </thead>
        <tbody>
          {stores.map((s) => {
            const st = STATUS[s.status];
            const place = [s.city, s.state].filter(Boolean).join(", ");
            return (
              <tr key={s.id}>
                <Td>
                  <button type="button" onClick={() => onView(s)} className="max-w-[16rem] truncate text-left font-semibold text-heading hover:text-brand-700 focus-visible:underline">
                    {s.name}
                  </button>
                  {s.crmCode && <div className="text-xs text-gray-500">{s.crmCode}</div>}
                </Td>
                <Td className="whitespace-nowrap">{s.externalCode}</Td>
                <Td><Badge tone={platformTone(s.partnerSlug)}>{s.partnerName ?? "None"}</Badge></Td>
                <Td className="whitespace-nowrap">{s.regionName ?? <span className="text-gray-400">None</span>}</Td>
                <Td>{place || <span className="text-gray-400">None</span>}</Td>
                <Td>
                  {s.vendorName ? <span className="font-medium text-brand-700">{s.vendorName}</span> : <span className="text-gray-400">None</span>}
                  {s.vendorNumber && <div className="text-xs text-gray-500">{s.vendorNumber}</div>}
                </Td>
                <Td><Badge tone={st.tone}>{st.label}</Badge></Td>
                <Td className="whitespace-nowrap text-right">
                  <Button size="sm" variant="secondary" onClick={() => onView(s)}>View</Button>
                  {canManage && <Button size="sm" variant="secondary" onClick={() => onEdit(s)} className="ml-1.5">Edit</Button>}
                  {canManage && s.status !== "CLOSE" && (
                    <Button size="sm" variant="ghost" onClick={() => onClose(s)} className="ml-1.5 text-status-danger hover:bg-status-danger-soft hover:text-status-danger">Close</Button>
                  )}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
