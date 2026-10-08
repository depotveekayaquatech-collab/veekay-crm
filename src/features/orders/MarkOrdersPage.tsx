import { distinctOptions } from "@/lib/options";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { IconMapPin, IconStore } from "@/components/ui/icons";
import { usePersistentState } from "@/hooks/usePersistentState";
import { usePermission } from "@/hooks/usePermission";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { OrderCalendar } from "@/features/orders/OrderCalendar";
import { QuickEntry } from "@/features/orders/QuickEntry";
import { RegionFilter, SegmentedControl, SelectStorePrompt, StorePicker } from "@/features/orders/ui";
import { useCalendar, useMarkOrder, useMyStores } from "@/features/orders/useOrders";
import type { MyStore } from "@/types/order";

function ContactCard({ label, name, phone }: { label: string; name: string | null; phone: string | null }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-surface-subtle px-3.5 py-3">
      <div className="min-w-0">
        <p className="text-[11px] font-bold uppercase tracking-wider text-gray-400">{label}</p>
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

function StoreSummary({ store }: { store: MyStore }) {
  const place = [store.city, store.state].filter(Boolean).join(", ");
  return (
    <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
      <div className="h-1.5 bg-gradient-to-r from-brand-500 to-aqua-400" />
      <div className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3.5">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-aqua-400 text-white shadow-md">
              <IconStore className="h-6 w-6" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h3 className="truncate text-lg font-extrabold text-heading">{store.name}</h3>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2.5 text-sm text-gray-500">
                <span className="font-semibold text-gray-700">{store.externalCode}</span>
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

export function MarkOrdersPage() {
  const { data: stores, isLoading, isError, refetch } = useMyStores();
  const [vendor, setVendor] = useState("");
  const [pickedPartner, setPartner] = usePersistentState<string>("orders.platform", "");
  const [region, setRegion] = useState("");
  const [params] = useSearchParams();
  const canMark = usePermission("orders.mark");
  const [pickedId, setStoreId] = useState(params.get("store") ?? "");
  // Someone with a single store has nothing to pick — open it straight away.
  const storeId = pickedId || (stores?.length === 1 ? stores[0].id : "");
  const [period, setPeriod] = useState<{ year?: number; month?: number }>({});
  const [savedView, setView] = usePersistentState<"quick" | "store">("orders.view", "quick");
  const view = params.get("store") || !canMark ? "store" : savedView;
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
          <span className="rounded-full bg-brand-50 px-3 py-1.5 text-xs font-bold text-brand-700">{partners[0].label}</span>
        )}
        {regions.length > 1 && <RegionFilter value={region} onChange={(v) => { setRegion(v); setStoreId(""); }} options={regions} className="sm:w-48 [&_label]:sr-only" />}
        {vendors.length > 1 && (
          <div className="w-full sm:w-48 [&_label]:sr-only">
            <Select label="Vendor" value={vendor} onChange={(e) => setVendor(e.target.value)} placeholder="All vendors" options={vendors} />
          </div>
        )}
      </div>

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
