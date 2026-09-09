import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { useAllStores } from "@/features/stores/useAllStores";
import { usePartners } from "@/features/stores/useStores";
import { OrderCalendar } from "@/features/orders/OrderCalendar";
import { useCalendar, useCorrectEntry } from "@/features/orders/useOrders";
import type { CalendarDay } from "@/types/order";

export function CorrectEntriesPage() {
  const { data: partners = [] } = usePartners();
  const { data: stores = [] } = useAllStores(true);
  const [partner, setPartner] = useState("");
  const [storeId, setStoreId] = useState("");
  const [editing, setEditing] = useState<CalendarDay | null>(null);
  const [value, setValue] = useState("");

  const correct = useCorrectEntry();
  const { data: calendar, isLoading } = useCalendar(storeId || null);

  const visibleStores = stores.filter((s) => !partner || s.partnerSlug === partner);

  function openDay(d: CalendarDay) {
    if (d.isFuture) return;
    setEditing(d);
    setValue(d.count === null ? "" : String(d.count));
  }

  async function save(clear = false) {
    if (!editing) return;
    const count = clear ? null : Number(value);
    if (!clear && (!Number.isInteger(count as number) || (count as number) < 0 || (count as number) > 200)) return;
    await correct.mutateAsync({ storeId, date: editing.date, count });
    setEditing(null);
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Correct entries" subtitle="Admins can overwrite or clear any day for any store." />

      <div className="grid gap-3 sm:max-w-lg sm:grid-cols-2">
        <Select
          label="Platform"
          value={partner}
          onChange={(e) => {
            setPartner(e.target.value);
            setStoreId("");
          }}
          placeholder="All platforms"
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
        />
        <Select
          label="Store"
          value={storeId}
          onChange={(e) => setStoreId(e.target.value)}
          placeholder="Select a store"
          options={visibleStores.map((s) => ({ value: s.id, label: `${s.name} (${s.externalCode})` }))}
        />
      </div>

      {storeId && (isLoading || !calendar) && <Skeleton className="h-80 lg:max-w-2xl" />}
      {storeId && calendar && (
        <div className="lg:max-w-2xl">
          <OrderCalendar calendar={calendar} onPickDay={openDay} />
        </div>
      )}

      {editing && (
        <Modal
          open
          onClose={() => setEditing(null)}
          title={`${editing.date}`}
          description={editing.marked ? `Currently ${editing.count} (by ${editing.source}).` : "Not marked yet."}
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
              <Button onClick={() => save(false)} isLoading={correct.isPending} disabled={value === ""}>
                Save
              </Button>
            </>
          }
        >
          <Input
            label="Bottle count"
            type="number"
            min={0}
            max={200}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
          />
        </Modal>
      )}
    </div>
  );
}
