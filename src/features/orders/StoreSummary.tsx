import { IconMapPin, IconStore } from "@/components/ui/icons";

/** What the header card needs to know about a store (the orders page and the review page both fill it in). */
export interface StoreSummaryData {
  name: string;
  externalCode: string;
  crmCode?: string | null;
  duplicateName?: boolean;
  city: string | null;
  state: string | null;
  partnerName: string | null;
  regionName: string | null;
  pocName: string | null;
  pocNumber: string | null;
  vendorName: string | null;
  vendorNumber: string | null;
}

function ContactCard({ label, name, phone }: { label: string; name: string | null; phone: string | null }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-surface-subtle px-3.5 py-3">
      <div className="min-w-0">
        <p className="text-[11px] font-bold text-gray-400">{label}</p>
        <p className="truncate text-sm font-semibold text-gray-900">{name ?? "—"}</p>
        {phone && <p className="text-xs tabular-nums text-gray-500">{phone}</p>}
      </div>
      {phone && (
        <a
          href={`tel:${phone}`}
          aria-label={`Call ${name ?? label}`}
          className="shrink-0 rounded-lg bg-brand-500/10 px-3 py-1.5 text-xs font-bold text-brand-600 transition-colors hover:bg-brand-500 hover:text-white"
        >
          Call
        </a>
      )}
    </div>
  );
}

/** The store card: name and codes, place, platform and region, and the store contact and vendor with a Call button. */
export function StoreSummary({ store }: { store: StoreSummaryData }) {
  const place = [store.city, store.state].filter(Boolean).join(", ");
  return (
    <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
      <div className="h-1.5 bg-brand-500" />
      <div className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3.5">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-md">
              <IconStore className="h-6 w-6" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h3 className="truncate text-lg font-extrabold text-heading">{store.name}</h3>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2.5 text-sm text-gray-500">
                <span className="font-semibold text-gray-700">{store.externalCode}</span>
                {store.crmCode && <span className="text-xs text-gray-400">{store.crmCode}</span>}
                {store.duplicateName && (
                  <span className="rounded-full bg-status-danger-soft px-2 py-0.5 text-xs font-bold text-status-danger">Listed twice in the CRM</span>
                )}
                {place && (
                  <span className="flex items-center gap-1">
                    <IconMapPin className="h-3.5 w-3.5" aria-hidden="true" />
                    {place}
                  </span>
                )}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {store.partnerName && <span className="rounded-full bg-brand-50 px-2.5 py-1 text-xs font-bold text-brand-700">{store.partnerName}</span>}
            {store.regionName && <span className="rounded-full bg-aqua-50 px-2.5 py-1 text-xs font-bold text-aqua-600">{store.regionName}</span>}
          </div>
        </div>
        {(store.pocName || store.vendorName) && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <ContactCard label="Store contact" name={store.pocName} phone={store.pocNumber} />
            <ContactCard label="Vendor" name={store.vendorName} phone={store.vendorNumber} />
          </div>
        )}
      </div>
    </div>
  );
}
