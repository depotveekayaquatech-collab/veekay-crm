import { useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { useAllRegions } from "@/features/regions/useRegions";
import { usePartners, useStoreMutations } from "@/features/stores/useStores";
import type { Store, StoreStatus } from "@/types/store";

interface Props {
  onClose: () => void;
  store?: Store | null;
}

const STATUSES: { value: StoreStatus; label: string }[] = [
  { value: "LIVE", label: "Live" },
  { value: "PENDING", label: "Pending" },
  { value: "CLOSE", label: "Closed" },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-surface-border bg-surface-subtle/60 p-4">
      <h3 className="mb-3 border-b border-surface-border pb-2 text-[11px] font-bold uppercase tracking-wider text-brand-700">{title}</h3>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

export function StoreFormModal({ onClose, store }: Props) {
  const { create, update } = useStoreMutations();
  const { data: regions = [] } = useAllRegions();
  const { data: partners = [] } = usePartners();
  const editing = Boolean(store);

  const [f, setF] = useState({
    name: store?.name ?? "",
    external_code: store?.externalCode ?? "",
    partner_organization_id: store?.partnerOrganizationId ?? "",
    region_id: store?.regionId ?? "",
    state: store?.state ?? "",
    city: store?.city ?? "",
    address: store?.address ?? "",
    poc_name: store?.pocName ?? "",
    poc_number: store?.pocNumber ?? "",
    vendor_name: store?.vendorName ?? "",
    vendor_number: store?.vendorNumber ?? "",
    start_date: store?.startDate ?? "",
    status: (store?.status ?? "LIVE") as StoreStatus,
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF((p) => ({ ...p, [k]: v }));

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const payload = {
      name: f.name,
      external_code: f.external_code,
      region_id: f.region_id || null,
      state: f.state || null,
      city: f.city || null,
      address: f.address || null,
      poc_name: f.poc_name || null,
      poc_number: f.poc_number || null,
      vendor_name: f.vendor_name || null,
      vendor_number: f.vendor_number || null,
      start_date: f.start_date || null,
      status: f.status,
    };
    try {
      if (store) {
        await update.mutateAsync({ id: store.id, input: payload });
      } else {
        await create.mutateAsync({ ...payload, partner_organization_id: f.partner_organization_id });
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  const busy = create.isPending || update.isPending;

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={editing ? "Edit store details" : "Add store"}
      description="Update store configuration and operational details."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" form="store-form" isLoading={busy}>
            {editing ? "Save changes" : "Add store"}
          </Button>
        </>
      }
    >
      <form id="store-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Section title="A. Store identity">
          <Input
            label={editing ? "Store ID (read-only)" : "Store ID"}
            value={f.external_code}
            onChange={(e) => set("external_code")(e.target.value)}
            hint={editing ? undefined : "The partner's own outlet ID, e.g. 4589"}
            readOnly={editing}
            required
          />
          <Input label="Store name" value={f.name} onChange={(e) => set("name")(e.target.value)} required autoFocus={!editing} />
        </Section>

        <Section title="B. Business classification">
          <Select
            label="Platform"
            value={f.partner_organization_id}
            onChange={(e) => set("partner_organization_id")(e.target.value)}
            placeholder="Select"
            options={partners.map((p) => ({ value: p.id, label: p.name }))}
            required
            disabled={editing}
          />
          <Select
            label="Region"
            value={f.region_id}
            onChange={(e) => set("region_id")(e.target.value)}
            placeholder="None (state-based)"
            options={regions.map((r) => ({ value: r.id, label: r.name }))}
          />
          <Select
            label="Status"
            value={f.status}
            onChange={(e) => set("status")(e.target.value)}
            options={STATUSES}
          />
          <Input
            label="Start date"
            type="date"
            value={f.start_date}
            onChange={(e) => set("start_date")(e.target.value)}
            max={new Date().toISOString().slice(0, 10)}
            hint="The day supply began. Earlier days are never counted as pending."
          />
          {store?.entity && <Input label="Entity (from the sheet)" value={store.entity} readOnly />}
        </Section>

        <Section title="C. Location details">
          <Input label="State" value={f.state} onChange={(e) => set("state")(e.target.value)} />
          <Input label="City" value={f.city} onChange={(e) => set("city")(e.target.value)} />
          <div className="sm:col-span-2">
            <Input label="Address" value={f.address} onChange={(e) => set("address")(e.target.value)} placeholder="Optional" />
          </div>
        </Section>

        <Section title="D. Vendor & contact assignment">
          <Input label="Vendor name" value={f.vendor_name} onChange={(e) => set("vendor_name")(e.target.value)} />
          <Input label="Vendor number" value={f.vendor_number} onChange={(e) => set("vendor_number")(e.target.value)} />
          <Input label="POC name" value={f.poc_name} onChange={(e) => set("poc_name")(e.target.value)} />
          <Input label="POC number" value={f.poc_number} onChange={(e) => set("poc_number")(e.target.value)} />
        </Section>

        {error && <p role="alert" className="text-sm text-status-danger">{error}</p>}
      </form>
    </Modal>
  );
}
