import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { checkCode, type CodeCheck, type VendorForm } from "@/features/vendorpay/adminApi";

interface Props {
  title: string;
  description?: string;
  initial: VendorForm;
  /** An existing vendor: the code is shown but cannot be edited. */
  codeLocked: boolean;
  isSaving: boolean;
  onClose: () => void;
  onSubmit: (form: VendorForm) => void;
}

/** Add or edit a vendor. The code is typed once, checked for duplicates, and then fixed for good. Remount (key) for each vendor. */
export function VendorFormModal({ title, description, initial, codeLocked, isSaving, onClose, onSubmit }: Props) {
  const [form, setForm] = useState(initial);
  const [check, setCheck] = useState<CodeCheck | null>(null);
  const set = (patch: Partial<VendorForm>) => setForm((f) => ({ ...f, ...patch }));

  async function runCheck() {
    if (codeLocked || !form.vendorCode.trim()) return setCheck(null);
    try {
      setCheck(await checkCode(form.vendorCode));
    } catch {
      setCheck(null);
    }
  }

  const codeProblem = check && (!check.valid || check.exists) ? check.message : null;
  const dateProblem = form.openingDate && !form.openingDate.endsWith("-01") ? "Use the 1st of a month." : undefined;
  const canSave = form.vendorCode.trim() && form.name.trim() && !codeProblem && !dateProblem && !isSaving;

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button isLoading={isSaving} disabled={!canSave} onClick={() => onSubmit(form)}>
            Save vendor
          </Button>
        </>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); if (canSave) onSubmit(form); }}>
        <Input
          label="Vendor code"
          value={form.vendorCode}
          disabled={codeLocked}
          onChange={(e) => { set({ vendorCode: e.target.value.toUpperCase() }); setCheck(null); }}
          onBlur={() => void runCheck()}
          error={codeProblem ?? undefined}
          hint={codeLocked ? "The code never changes after the vendor is created." : check?.valid && !check.exists ? "This code is free." : "The same code the account name ends with in Busy, e.g. V0123."}
          maxLength={32}
        />
        <Input label="Name" value={form.name} onChange={(e) => set({ name: e.target.value })} maxLength={160} />
        <Input label="City" value={form.city} onChange={(e) => set({ city: e.target.value })} maxLength={80} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input label="Opening balance (₹)" inputMode="decimal" value={form.openingBalance} onChange={(e) => set({ openingBalance: e.target.value })} hint="What you owed this vendor on the opening date." />
          <Input label="Opening date" type="date" value={form.openingDate} onChange={(e) => set({ openingDate: e.target.value })} error={dateProblem} hint="The 1st of a month. Leave blank if there is no opening balance." />
        </div>
      </form>
    </Modal>
  );
}
