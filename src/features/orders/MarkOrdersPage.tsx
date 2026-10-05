import { distinctOptions } from "@/lib/options";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { IconMapPin, IconUpload } from "@/components/ui/icons";
import { usePermission } from "@/hooks/usePermission";
import { ImportOrdersModal } from "@/features/orders/ImportOrdersModal";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { OrderCalendar } from "@/features/orders/OrderCalendar";
import { QuickEntry } from "@/features/orders/QuickEntry";
import { RegionFilter, SegmentedControl, SelectStorePrompt, StorePicker } from "@/features/orders/ui";
import { useCalendar, useMarkOrder, useMyStores } from "@/features/orders/useOrders";
import type { MyStore } from "@/types/order";

function Phone({ value }: { value: string | null }) {
  if (!value) return null;
  return (
    <a href={`tel:${value}`} className="font-medium text-brand-600 hover:text-brand-700">
      {value}
    </a>
  );
}

function StoreSummary({ store }: { store: MyStore }) {
  const place = [store.city, store.state].filter(Boolean).join(", ");
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-4 shadow-card sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-lg font-bold text-heading">{store.name}</h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-gray-500">
            <span className="font-medium text-gray-700">{store.externalCode}</span>
            {place && (
              <span className="flex items-center gap-1">
                <IconMapPin className="h-3.5 w-3.5" />
                {place}
              </span>
            )}
          </p>
        </div>
        {store.regionName && (
          <span className="rounded-full bg-aqua-50 px-2.5 py-1 text-xs font-semibold text-aqua-600 ring-1 ring-inset ring-aqua-200">
            {store.regionName}
          </span>
        )}
      </div>
      {(store.pocName || store.vendorName) && (
        <dl className="mt-4 grid gap-3 border-t border-surface-border pt-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Store contact</dt>
            <dd className="mt-0.5 text-gray-900">{store.pocName ?? "—"} <Phone value={store.pocNumber} /></dd>
          </div>
          <div>
            <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Vendor</dt>
            <dd className="mt-0.5 text-gray-900">{store.vendorName ?? "—"} <Phone value={store.vendorNumber} /></dd>
          </div>
        </dl>
      )}
    </div>
  );
}

export function MarkOrdersPage() {
  const { data: stores, isLoading, isError, refetch } = useMyStores();
  const [vendor, setVendor] = useState("");
  const [pickedPartner, setPartner] = useState("");
  const [region, setRegion] = useState("");
  const [params] = useSearchParams();
  const canMark = usePermission("orders.mark");
  const [pickedId, setStoreId] = useState(params.get("store") ?? "");
  // Someone with a single store has nothing to pick — open it straight away.
  const storeId = pickedId || (stores?.length === 1 ? stores[0].id : "");
  const [period, setPeriod] = useState<{ year?: number; month?: number }>({});
  const [importing, setImporting] = useState(false);
  const [view, setView] = useState<"quick" | "store">(params.get("store") || !canMark ? "store" : "quick");
  const canImport = usePermission("orders.correct");
  const mark = useMarkOrder();
  const { data: calendar, isLoading: calLoading, isError: calError, refetch: refetchCal } = useCalendar(
    storeId || null,
    period.year,
    period.month,
  );

  const partners = useMemo(
    () => distinctOptions(stores ?? [], (s) => (s.partnerSlug ? { value: s.partnerSlug, label: s.partnerName ?? s.partnerSlug } : null)),
    [stores],
  );
  // Platforms are kept apart: one is always selected (the first, unless the user picks another).
  const partner = partners.some((p) => p.value === pickedPartner) ? pickedPartner : (partners[0]?.value ?? "");

  const ofPartner = useMemo(() => (stores ?? []).filter((s) => !partner || s.partnerSlug === partner), [stores, partner]);
  const regions = useMemo(
    () => distinctOptions(ofPartner, (s) => (s.regionId ? { value: s.regionId, label: s.regionName ?? "Region" } : null)),
    [ofPartner],
  );
  const vendors = useMemo(() => distinctOptions(ofPartner, (s) => (s.vendorName ? { value: s.vendorName.toLowerCase(), label: s.vendorName } : null)), [ofPartner]);

  const filtered = useMemo(
    () =>
      ofPartner.filter(
        (s) =>
          (!region || s.regionId === region) && (!vendor || (s.vendorName ?? "").toLowerCase() === vendor),
      ),
    [ofPartner, region, vendor],
  );

  const selectedStore = stores?.find((s) => s.id === storeId) ?? null;

  function choose(id: string) {
    setStoreId(id);
    setPeriod({});
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        {canMark && <SegmentedControl
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: "quick", label: "Quick entry" },
            { value: "store", label: "By store" },
          ]}
        />}
        {partners.length > 1 && (
          <SegmentedControl
            label="Platform"
            value={partner}
            onChange={(v) => {
              setPartner(v);
              setRegion("");
              setVendor("");
              setStoreId("");
            }}
            options={partners}
          />
        )}
        {partners.length === 1 && (
          <span className="rounded-full bg-aqua-50 px-3 py-1.5 text-xs font-semibold text-aqua-600 ring-1 ring-inset ring-aqua-200">{partners[0].label}</span>
        )}
        {regions.length > 1 && <RegionFilter value={region} onChange={(v) => { setRegion(v); setStoreId(""); }} options={regions} className="sm:w-48 [&_label]:sr-only" />}
        {vendors.length > 1 && (
          <div className="w-full sm:w-48 [&_label]:sr-only">
            <Select label="Vendor" value={vendor} onChange={(e) => setVendor(e.target.value)} placeholder="All vendors" options={vendors} />
          </div>
        )}
        {canImport && (
          <Button variant="secondary" className="ml-auto" onClick={() => setImporting(true)}>
            <IconUpload className="h-4 w-4" />
            Import order sheet
          </Button>
        )}
      </div>
      {importing && <ImportOrdersModal onClose={() => setImporting(false)} />}

      {isLoading && (
        <div className="grid gap-5 lg:grid-cols-[21rem_1fr]">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      )}
      {isError && <ErrorState message="Couldn't load your stores." onRetry={() => refetch()} />}

      {stores && stores.length === 0 && (
        <EmptyState title="No stores assigned yet" description={canMark ? "An admin needs to assign you a region or states." : "There are no live stores on your platform yet."} />
      )}

      {stores && stores.length > 0 && canMark && view === "quick" && <QuickEntry stores={filtered} />}

      {stores && stores.length > 0 && (view === "store" || !canMark) && (
        <div className="grid items-start gap-5 lg:grid-cols-[21rem_1fr]">
          <StorePicker
            title={canMark ? "Your stores" : "Stores"}
            stores={filtered}
            selectedId={storeId}
            onSelect={choose}
          />

          <div className="flex min-w-0 flex-col gap-5">
            {!selectedStore && <SelectStorePrompt text={canMark ? "Pick one of your stores to log its daily bottle count." : "Pick a store to see its daily entries."} />}
            {selectedStore && (
              <>
                <StoreSummary store={selectedStore} />
                {calError ? (
                  <ErrorState message="Couldn't load this store's calendar." onRetry={() => refetchCal()} />
                ) : calLoading || !calendar ? (
                  <Skeleton className="h-96" />
                ) : (
                  <OrderCalendar
                    calendar={calendar}
                    marking={mark.isPending}
                    onNavigate={(year, month) => setPeriod({ year, month })}
                    onMark={canMark ? (date, count) => mark.mutateAsync({ storeId: selectedStore.id, date, count }) : undefined}
                  />
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
