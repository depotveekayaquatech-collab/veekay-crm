import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { SearchBox } from "@/features/orders/ui";
import { ceilQty, useAdjust, useStoreChoices, type ApplyResult, type Preview } from "@/features/datasync/cashApi";
import { daysAgo } from "@/lib/dates";

const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });

export function AdjustTab() {
  const today = daysAgo(0);
  const [amount, setAmount] = useState("");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(today);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [override, setOverride] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<ApplyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: stores = [] } = useStoreChoices(q);
  const { preview: previewM, apply } = useAdjust();

  const auto = ceilQty(amount, price);
  const input = useMemo(
    () => ({ storeIds: [...picked], purchaseDate: date, amount, pricePerItem: price, quantity: override !== "" ? Number(override) : null }),
    [picked, date, amount, price, override],
  );

  function toggle(id: string) {
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  async function onPreview() {
    setError(null);
    setResult(null);
    if (!(Number(amount) > 0)) return setError("Enter the cash purchase amount.");
    if (!(Number(price) > 0)) return setError("Enter the price per item.");
    if (!date || date > today) return setError("Pick a valid purchase date (not in the future).");
    if (picked.size === 0) return setError("Select at least one store.");
    if (override !== "" && (!/^\d+$/.test(override) || Number(override) < 1)) return setError("The final quantity must be a whole number, at least 1.");
    try {
      setPreview(await previewM.mutateAsync(input));
    } catch {
      /* the API layer already showed the reason */
    }
  }

  async function onApply() {
    try {
      const r = await apply.mutateAsync(input);
      setResult(r);
      setPreview(null);
      setPicked(new Set());
      setAmount("");
      setOverride("");
    } catch {
      /* shown by the API layer */
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-4 rounded-2xl border border-surface-border bg-surface p-5 shadow-card">
        <div>
          <h3 className="text-base font-bold text-heading">Cash purchase adjustment</h3>
          <p className="mt-1 text-sm text-gray-500">
            The bottles bought with cash are <b>added</b> to each store's existing order for that date. The employee's own entry is never replaced.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Input label="Cash purchase amount (₹)" type="number" inputMode="decimal" min="0" step="0.01" value={amount} onChange={(e) => { setAmount(e.target.value); setOverride(""); }} />
          <Input label="Price per item (₹)" type="number" inputMode="decimal" min="0" step="0.01" value={price} onChange={(e) => { setPrice(e.target.value); setOverride(""); }} />
          <Input label="Cash purchase date" type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl bg-surface-subtle px-4 py-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">Automatic quantity</p>
            <p className="mt-1 text-2xl font-bold tabular-nums text-heading">{auto ?? "—"}</p>
            <p className="text-xs text-gray-500">Amount ÷ price, always rounded up</p>
          </div>
          <Input
            label="Final quantity (per store)"
            type="number"
            min="1"
            step="1"
            value={override !== "" ? override : auto !== null ? String(auto) : ""}
            onChange={(e) => setOverride(e.target.value)}
            hint="Change it only if the calculated number isn't right."
          />
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[13px] font-semibold text-gray-700">Select stores ({picked.size} selected)</p>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" type="button" onClick={() => setPicked((p) => new Set([...p, ...stores.map((s) => s.id)]))} disabled={!stores.length}>
                Select all shown
              </Button>
              <Button size="sm" variant="ghost" type="button" onClick={() => setPicked(new Set())} disabled={!picked.size}>
                Clear
              </Button>
            </div>
          </div>
          <SearchBox value={q} onChange={setQ} placeholder="Search stores by name, ID, city or state" />
          <ul className="max-h-72 divide-y divide-surface-border overflow-auto rounded-xl border border-surface-border">
            {stores.map((s) => (
              <li key={s.id}>
                <label className="flex cursor-pointer items-center gap-3 px-4 py-2.5 text-sm hover:bg-surface-subtle">
                  <input type="checkbox" className="h-4 w-4" checked={picked.has(s.id)} onChange={() => toggle(s.id)} />
                  <span className="font-medium text-gray-900">{s.name}</span>
                  <span className="text-xs text-gray-500">
                    {s.code} · {s.platform} · {s.state}
                  </span>
                </label>
              </li>
            ))}
            {!stores.length && <li className="px-4 py-6 text-center text-sm text-gray-500">No stores match.</li>}
          </ul>
        </div>

        {error && (
          <p role="alert" className="text-sm text-status-danger">
            {error}
          </p>
        )}
        <div>
          <Button onClick={onPreview} isLoading={previewM.isPending}>
            Preview changes
          </Button>
        </div>
      </section>

      {result && (
        <section className="flex flex-col gap-2 rounded-2xl border border-surface-border bg-surface p-5 text-sm shadow-card">
          <p className="font-bold text-heading">
            Applied +{result.finalQty} to {result.applied.length} store{result.applied.length === 1 ? "" : "s"}
          </p>
          <ul className="text-gray-600">
            {result.applied.map((r) => (
              <li key={r.storeId}>
                {r.outletName}: {r.previous} → <b>{r.newTotal}</b>
              </li>
            ))}
          </ul>
          {result.failed.length > 0 && (
            <ul className="list-disc rounded-lg bg-status-danger-soft px-4 py-2 pl-8 text-status-danger">
              {result.failed.map((f) => (
                <li key={f.outletCode}>
                  Not updated: {f.outletName} — {f.error}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <Modal
        open={Boolean(preview)}
        onClose={() => setPreview(null)}
        title="Confirm changes"
        description={preview ? `${day(preview.purchaseDate)} · ₹${preview.amount} at ₹${preview.pricePerItem} per item` : undefined}
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setPreview(null)}>
              Cancel
            </Button>
            <Button onClick={onApply} isLoading={apply.isPending} disabled={!preview?.canApply}>
              Apply changes
            </Button>
          </>
        }
      >
        {preview && (
          <div className="flex flex-col gap-4 text-sm">
            <p className="text-gray-600">
              Automatic quantity <b>{preview.autoQty}</b> · quantity added per store <b>{preview.finalQty}</b>
              {preview.overridden && " (changed by you)"} · stores <b>{preview.totalStores}</b>
            </p>
            <ul className="divide-y divide-surface-border rounded-xl border border-surface-border">
              {preview.rows.map((r) => (
                <li key={r.storeId} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                  <span>
                    <span className="font-medium text-gray-900">{r.outletName}</span>
                    <span className="ml-2 text-xs text-gray-500">{r.outletCode}</span>
                    {!r.hasEntry && <span className="ml-2 text-xs text-gray-500">(no entry yet)</span>}
                    {r.error && <span className="mt-0.5 block text-xs text-status-danger">{r.error}</span>}
                  </span>
                  <span className="tabular-nums">
                    {r.previous} → <b>{r.newTotal}</b>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Modal>
    </div>
  );
}
