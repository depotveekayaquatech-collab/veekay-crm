import { useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { SegmentedControl } from "@/features/orders/ui";
import { useAddCashPurchase, type CashOptions, type PurchaseKind } from "@/features/cash/api";
import { daysAgo } from "@/lib/dates";

const MAX_PROOF_MB = 10;

export function AddPurchaseModal({ options, onClose }: { options: CashOptions; onClose: () => void }) {
  const add = useAddCashPurchase();
  const today = daysAgo(0);
  const [kind, setKind] = useState<PurchaseKind>("OFFICE");
  const [storeId, setStoreId] = useState("");
  const [date, setDate] = useState(today);
  const [category, setCategory] = useState("");
  const [otherReason, setOtherReason] = useState("");
  const [amount, setAmount] = useState("");
  const [proof, setProof] = useState<File | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reasons = kind === "OFFICE" ? options.officeReasons : options.storeReasons;
  const reasonOptions = useMemo(() => reasons.map((r) => ({ value: r.code, label: r.label })), [reasons]);
  const storeOptions = useMemo(
    () => options.stores.map((s) => ({ value: s.id, label: `${s.name} (${s.code})` })),
    [options.stores],
  );

  function changeKind(next: PurchaseKind) {
    setKind(next);
    setCategory(""); // the two lists differ
    setOtherReason("");
    setError(null);
  }

  function pickProof(f: File | undefined) {
    if (!f) return;
    const ok = /^(image\/(jpeg|png|webp)|application\/pdf)$/.test(f.type);
    if (!ok) return setError("Payment proof must be a JPG, PNG or WEBP photo, or a PDF.");
    if (f.size > MAX_PROOF_MB * 1024 * 1024) return setError(`The file is larger than ${MAX_PROOF_MB} MB.`);
    setError(null);
    setProof(f);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const value = Number(amount);
    if (kind === "STORE" && !storeId) return setError("Pick the store this purchase was for.");
    if (!category) return setError("Pick a reason.");
    if (category === "OTHER" && otherReason.trim().length < 3) return setError("Describe what the purchase was for.");
    if (!Number.isFinite(value) || value <= 0) return setError("Enter the amount paid.");
    if (value > Number(options.maxAmount)) return setError(`The amount can't be more than ${Number(options.maxAmount).toLocaleString("en-IN")}.`);
    if (!proof) return setError("Attach the payment proof (bill, receipt or UPI / payment screenshot).");
    try {
      await add.mutateAsync({ kind, storeId: storeId || null, purchaseDate: date, category, otherReason, amount: value.toFixed(2), notes, proof });
      onClose();
    } catch {
      /* the API layer already showed the reason */
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Add cash purchase"
      description="Record money paid in cash for the office or for a store."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button type="submit" form="cash-purchase-form" isLoading={add.isPending}>
            Save purchase
          </Button>
        </>
      }
    >
      <form id="cash-purchase-form" onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <SegmentedControl
          label="Purchase for"
          value={kind}
          onChange={changeKind}
          options={[
            { value: "OFFICE", label: "Office" },
            { value: "STORE", label: "A store" },
          ]}
        />
        {kind === "STORE" && (
          <Select
            label="Store"
            searchable
            value={storeId}
            onChange={(e) => setStoreId(e.target.value)}
            options={storeOptions}
            placeholder={storeOptions.length ? "Search or select a store" : "No stores available to you"}
          />
        )}
        {kind === "STORE" && <p className="-mb-2 text-sm text-gray-500">Item: <span className="font-medium text-gray-800">Water bottles</span></p>}
        <Select label={kind === "STORE" ? "Reason for cash purchase" : "Purchase"} value={category} onChange={(e) => setCategory(e.target.value)} options={reasonOptions} placeholder={kind === "STORE" ? "Why was it bought in cash?" : "Select what was bought"} />
        {category === "OTHER" && (
          <Input
            label={kind === "STORE" ? "Describe the reason" : "Describe the purchase"}
            value={otherReason}
            maxLength={300}
            onChange={(e) => setOtherReason(e.target.value)}
            placeholder={kind === "STORE" ? "Why was it bought in cash?" : "What was bought and why"}
            autoFocus
          />
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Amount (₹)" type="number" inputMode="decimal" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          <Input label="Date" type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-semibold text-gray-700">Payment proof</span>
          <FileDropzone file={proof} onPick={pickProof} accept="image/jpeg,image/png,image/webp,application/pdf" hint={`Bill, receipt or payment screenshot · photo or PDF · up to ${MAX_PROOF_MB} MB`} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="cash-notes" className="text-[13px] font-semibold text-gray-700">
            Notes (optional)
          </label>
          <textarea
            id="cash-notes"
            rows={2}
            maxLength={1000}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full rounded-lg border border-surface-border bg-surface px-3.5 py-2.5 text-sm text-gray-900 shadow-sm outline-none transition-colors placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-status-danger">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
