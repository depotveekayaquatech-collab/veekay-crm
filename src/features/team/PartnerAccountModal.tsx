import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { usePartners } from "@/features/stores/useStores";
import { useTeamMutations } from "@/features/team/useTeam";
import type { Employee } from "@/types/employee";

/** The only things a partner login can ever be given — the server rejects anything else. */
const PARTNER_ACCESS = [
  { code: "orders.view", label: "Daily entries, vendors & store cards", hint: "Sees every live store on their platform: each store's daily bottle count, vendor contacts and printable cards." },
  { code: "tickets.view", label: "View tickets", hint: "Follows the tickets for their platform's stores and can comment on them." },
  { code: "reports.delivery", label: "Download delivery reports", hint: "Can download an Excel sheet of bottles delivered per store per day. Download only — nothing is shown on screen, and there are no totals." },
  { code: "tickets.create", label: "Raise tickets", hint: "Can report late or missed deliveries, quality problems and so on." },
];

export function PartnerAccountModal({ onClose, account }: { onClose: () => void; account?: Employee | null }) {
  const editing = Boolean(account);
  const { create, update, setPermissions } = useTeamMutations();
  const { data: partners = [] } = usePartners();

  const [code, setCode] = useState(account?.employeeCode ?? "");
  const [name, setName] = useState(account?.fullName ?? "");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState(account?.email ?? "");
  const [platformId, setPlatformId] = useState(account?.platformId ?? "");
  const [perms, setPerms] = useState<Set<string>>(new Set(account ? account.directPermissions : PARTNER_ACCESS.map((p) => p.code)));
  const [error, setError] = useState<string | null>(null);

  function toggle(c: string) {
    setPerms((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!platformId) return setError("Choose which platform this account belongs to.");
    try {
      if (account) {
        await update.mutateAsync({ id: account.id, input: { full_name: name, email: email || null } });
        await setPermissions.mutateAsync({ id: account.id, codes: [...perms] });
      } else {
        await create.mutateAsync({
          employee_code: code,
          full_name: name,
          password,
          email: email || null,
          platform_id: platformId,
          permission_codes: [...perms],
          account_type: "partner",
        });
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  const busy = create.isPending || update.isPending || setPermissions.isPending;

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? `Edit ${account?.employeeCode}` : "New partner account"}
      description="A login for Blinkit or Zepto. It only ever sees its own platform's stores."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" form="partner-form" isLoading={busy}>{editing ? "Save" : "Create account"}</Button>
        </>
      }
    >
      <form id="partner-form" onSubmit={submit} className="flex flex-col gap-4">
        <Select
          label="Platform"
          value={platformId}
          onChange={(e) => setPlatformId(e.target.value)}
          placeholder="Choose Blinkit or Zepto"
          options={partners.map((p) => ({ value: p.id, label: p.name }))}
          disabled={editing}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Login ID"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="e.g. BLINKIT01"
            required
            disabled={editing}
          />
          <Input label="Contact name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Person or team" required />
        </div>
        {!editing && (
          <Input
            label="Initial password"
            type="text"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            hint="At least 8 characters. They must choose their own at first sign-in."
            required
            minLength={8}
          />
        )}
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Optional" />

        <div>
          <p className="mb-2 text-sm font-medium text-gray-700">What this account can see and do</p>
          <div className="flex flex-col gap-2">
            {PARTNER_ACCESS.map((p) => (
              <label key={p.code} className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3.5 py-3 transition-colors ${perms.has(p.code) ? "border-brand-200 bg-brand-50/50" : "border-surface-border hover:bg-surface-subtle"}`}>
                <input
                  type="checkbox"
                  checked={perms.has(p.code)}
                  onChange={() => toggle(p.code)}
                  className="mt-0.5 h-4 w-4 rounded border-surface-border text-brand-500 focus:ring-brand-500"
                />
                <span>
                  <span className="block text-sm font-semibold text-gray-900">{p.label}</span>
                  <span className="block text-xs text-gray-500">{p.hint}</span>
                </span>
              </label>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-500">Partner accounts never see other platforms, employee performance, billing or compliance documents.</p>
        </div>

        {error && <p className="text-sm text-status-danger">{error}</p>}
      </form>
    </Modal>
  );
}
