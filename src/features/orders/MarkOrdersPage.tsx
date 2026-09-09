import { useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { OrderCalendar } from "@/features/orders/OrderCalendar";
import { useCalendar, useMarkOrder, useMyStores } from "@/features/orders/useOrders";

export function MarkOrdersPage() {
  const { data: stores, isLoading, isError, refetch } = useMyStores();
  const [vendor, setVendor] = useState("");
  const [storeId, setStoreId] = useState("");
  const mark = useMarkOrder();
  const { data: calendar, isLoading: calLoading } = useCalendar(storeId || null);

  const vendors = useMemo(() => {
    const set = new Map<string, string>();
    (stores ?? []).forEach((s) => {
      if (s.vendorName) set.set(s.vendorName.toLowerCase(), s.vendorName);
    });
    return [...set.values()].sort();
  }, [stores]);

  const filtered = useMemo(
    () =>
      (stores ?? []).filter((s) => !vendor || (s.vendorName ?? "").toLowerCase() === vendor.toLowerCase()),
    [stores, vendor],
  );

  const selectedStore = stores?.find((s) => s.id === storeId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Mark orders" subtitle="Log the daily bottle count for each of your stores." />

      {isLoading && <Skeleton className="h-24" />}
      {isError && <ErrorState message="Couldn't load your stores." onRetry={() => refetch()} />}

      {stores && stores.length === 0 && (
        <EmptyState title="No stores assigned yet" description="An admin needs to assign you a region or states." />
      )}

      {stores && stores.length > 0 && (
        <>
          <div className="grid gap-3 sm:max-w-lg sm:grid-cols-2">
            {vendors.length > 1 && (
              <Select
                label="Vendor"
                value={vendor}
                onChange={(e) => setVendor(e.target.value)}
                placeholder="All vendors"
                options={vendors.map((v) => ({ value: v, label: v }))}
              />
            )}
            <Select
              label="Store"
              value={storeId}
              onChange={(e) => setStoreId(e.target.value)}
              placeholder="Select a store"
              options={filtered.map((s) => ({ value: s.id, label: `${s.name} (${s.externalCode})` }))}
            />
          </div>

          {selectedStore && (
            <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
              <div>
                {calLoading || !calendar ? (
                  <Skeleton className="h-80" />
                ) : (
                  <OrderCalendar
                    calendar={calendar}
                    marking={mark.isPending}
                    onMark={(date, count) => mark.mutateAsync({ storeId: selectedStore.id, date, count })}
                  />
                )}
              </div>
              <aside className="h-fit rounded-lg border border-surface-border bg-white p-4 text-sm shadow-card">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Store details</p>
                <dl className="mt-2 space-y-1.5">
                  <div className="flex justify-between gap-2"><dt className="text-gray-500">Code</dt><dd className="text-gray-900">{selectedStore.externalCode}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-gray-500">City</dt><dd className="text-gray-900">{selectedStore.city ?? "—"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-gray-500">State</dt><dd className="text-gray-900">{selectedStore.state ?? "—"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-gray-500">Region</dt><dd className="text-gray-900">{selectedStore.regionName ?? "—"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-gray-500">POC</dt><dd className="text-gray-900">{selectedStore.pocName ?? "—"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-gray-500">Vendor</dt><dd className="text-gray-900">{selectedStore.vendorName ?? "—"}</dd></div>
                </dl>
              </aside>
            </div>
          )}
        </>
      )}
    </div>
  );
}
