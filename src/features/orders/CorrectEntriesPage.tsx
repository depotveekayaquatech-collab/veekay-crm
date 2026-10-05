import { distinctOptions } from "@/lib/options";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useAllStores } from "@/features/stores/useAllStores";
import { usePartners } from "@/features/stores/useStores";
import { OrderCalendar } from "@/features/orders/OrderCalendar";
import { RegionFilter, SegmentedControl, SelectStorePrompt, StorePicker } from "@/features/orders/ui";
import { useCalendar, useCorrectEntry } from "@/features/orders/useOrders";
import type { CalendarDay } from "@/types/order";

export function CorrectEntriesPage() {
  const { data: partners = [] } = usePartners();
  const { data: stores = [], isLoading: storesLoading } = useAllStores(true);
  const [pickedPartner, setPartner] = useState("");
  const [region, setRegion] = useState("");
  const partner = partners.some((p) => p.slug === pickedPartner) ? pickedPartner : (partners[0]?.slug ?? "");
  const [storeId, setStoreId] = useState("");
  const [period, setPeriod] = useState<{ year?: number; month?: number }>({});
  const [editing, setEditing] = useState<CalendarDay | null>(null);
  const [value, setValue] = useState("");

  const correct = useCorrectEntry();
  const { data: calendar, isLoading, isError, refetch } = useCalendar(storeId || null, period.year, period.month);

  const ofPartner = useMemo(() => stores.filter((s) => s.partnerSlug === partner), [stores, partner]);
  const regions = useMemo(
    () => distinctOptions(ofPartner, (s) => (s.regionId ? { value: s.regionId, label: s.regionName ?? "Region" } : null)),
    [ofPartner],
  );
  const visible = useMemo(
    () => ofPartner.filter((s) => !region || s.regionId === region).map((s) => ({ ...s, partnerName: null })),
    [ofPartner, region],
  );
  const selected = stores.find((s) => s.id === storeId) ?? null;

  function openDay(d: CalendarDay) {
    if (d.isFuture) return;
    setEditing(d);
    setValue(d.count === null ? "" : String(d.count));
  }

  const n = Number(value);
  const valid = value !== "" && Number.isInteger(n) && n >= 0 && n <= 200;

  async function save(clear = false) {
    if (!editing) return;
    if (!clear && !valid) return;
    await correct.mutateAsync({ storeId, date: editing.date, count: clear ? null : n });
    setEditing(null);
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-status-warning/25 bg-status-warning-soft/60 px-4 py-3 text-sm text-status-warning">
        <span className="font-semibold">Admin tool.</span>
        <span className="text-gray-700">Overwrite or clear any day for any store. Every change is recorded in the activity log.</span>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[21rem_1fr]">
        {storesLoading ? (
          <Skeleton className="h-96" />
        ) : (
          <StorePicker
            title="All stores"
            stores={visible}
            selectedId={storeId}
            onSelect={(id) => {
              setStoreId(id);
              setPeriod({});
            }}
            filters={
              <>
                <SegmentedControl
                  label="Platform"
                  value={partner}
                  onChange={(v) => {
                    setPartner(v);
                    setRegion("");
                    setStoreId("");
                  }}
                  options={partners.map((p) => ({ value: p.slug, label: p.name }))}
                />
                <RegionFilter
                  value={region}
                  onChange={(v) => {
                    setRegion(v);
                    setStoreId("");
                  }}
                  options={regions}
                  className="!w-full"
                />
              </>
            }
          />
        )}

        <div className="flex min-w-0 flex-col gap-5">
          {!storeId && <SelectStorePrompt text="Pick a store, then tap any past day to change or clear its count." />}
          {storeId && selected && (
            <div className="rounded-xl border border-surface-border bg-surface px-4 py-3.5 shadow-card sm:px-5">
              <h3 className="text-lg font-bold text-heading">{selected.name}</h3>
              <p className="text-sm text-gray-500">
                {selected.externalCode}
                {selected.partnerName ? ` · ${selected.partnerName}` : ""}
                {selected.city ? ` · ${selected.city}` : ""}
              </p>
            </div>
          )}
          {storeId && isError && <ErrorState message="Couldn't load this store's calendar." onRetry={() => refetch()} />}
          {storeId && !isError && (isLoading || !calendar) && <Skeleton className="h-96" />}
          {storeId && calendar && (
            <OrderCalendar calendar={calendar} onPickDay={openDay} onNavigate={(year, month) => setPeriod({ year, month })} />
          )}
        </div>
      </div>

      {editing && (
        <Modal
          open
          onClose={() => setEditing(null)}
          title={editing.date}
          description={editing.marked ? `Currently ${editing.count} bottles (by ${editing.source}).` : "Not marked yet."}
          size="sm"
          footer={
            <>
              {editing.marked && (
                <Button variant="danger" onClick={() => save(true)} isLoading={correct.isPending}>
                  Clear
                </Button>
              )}
              <Button variant="secondary" onClick={() => setEditing(null)} disabled={correct.isPending}>
                Cancel
              </Button>
              <Button onClick={() => save(false)} isLoading={correct.isPending} disabled={!valid}>
                Save
              </Button>
            </>
          }
        >
          <Input
            label="Bottle count"
            type="number"
            inputMode="numeric"
            min={0}
            max={200}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void save(false)}
            hint="0–200. Zero is a valid count."
            autoFocus
          />
        </Modal>
      )}
    </div>
  );
}
