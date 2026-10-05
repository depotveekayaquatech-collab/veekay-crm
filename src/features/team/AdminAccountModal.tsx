import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { usePermissionGroups, useTeamMutations } from "@/features/team/useTeam";
import type { Employee } from "@/types/employee";

type Level = "full" | "custom";

const LEVELS: { id: Level; title: string; text: string }[] = [
  { id: "full", title: "Full admin", text: "Everything an admin can do, including creating other admins and managing their access." },
  { id: "custom", title: "Custom admin", text: "Only what you tick below. They can't create admins or hand out permissions they don't have." },
];

export function AdminAccountModal({ onClose, account }: { onClose: () => void; account?: Employee | null }) {
  const editing = Boolean(account);
  const { create, update, setPermissions, setAdminAccess } = useTeamMutations();
  const { data: groups = [] } = usePermissionGroups();

  const [code, setCode] = useState(account?.employeeCode ?? "");
  const [name, setName] = useState(account?.fullName ?? "");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState(account?.email ?? "");
  const [level, setLevel] = useState<Level>(account?.adminLevel ?? "full");
  const [perms, setPerms] = useState<Set<string>>(new Set(account?.directPermissions ?? []));
  const [error, setError] = useState<string | null>(null);

  function toggle(c: string) {
    setPerms((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  }

  function toggleGroup(codes: string[], on: boolean) {
    setPerms((prev) => {
      const next = new Set(prev);
      codes.forEach((c) => (on ? next.add(c) : next.delete(c)));
      return next;
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (level === "custom" && perms.size === 0) return setError("Tick at least one thing this admin can do, or make them a full admin.");
    try {
      if (account) {
        await update.mutateAsync({ id: account.id, input: { full_name: name, email: email || null } });
        if (level !== account.adminLevel) await setAdminAccess.mutateAsync({ id: account.id, full: level === "full" });
        if (level === "custom") await setPermissions.mutateAsync({ id: account.id, codes: [...perms] });
      } else {
        await create.mutateAsync({
          employee_code: code,
          full_name: name,
          password,
          email: email || null,
          account_type: "admin",
          admin_access: level,
          permission_codes: level === "custom" ? [...perms] : [],
        });
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  const busy = create.isPending || update.isPending || setPermissions.isPending || setAdminAccess.isPending;

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={editing ? `Edit admin ${account?.employeeCode}` : "New admin"}
      description="Admins sign in with their ID like everyone else. Choose how much power this one gets."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" form="admin-form" isLoading={busy}>{editing ? "Save" : "Create admin"}</Button>
        </>
      }
    >
      <form id="admin-form" onSubmit={submit} className="flex flex-col gap-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Login ID" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="e.g. ADMIN004" required disabled={editing} autoFocus={!editing} />
          <Input label="Full name" value={name} onChange={(e) => setName(e.target.value)} required />
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
          <p className="mb-2 text-sm font-medium text-gray-700">Admin power</p>
          <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Admin power">
            {LEVELS.map((l) => (
              <label
                key={l.id}
                className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3.5 transition-colors ${
                  level === l.id ? "border-brand-300 bg-brand-50/60 ring-1 ring-brand-200" : "border-surface-border hover:bg-surface-subtle"
                }`}
              >
                <input type="radio" name="level" checked={level === l.id} onChange={() => setLevel(l.id)} className="mt-1 accent-brand-500" />
                <span>
                  <span className="block text-sm font-bold text-heading">{l.title}</span>
                  <span className="block text-xs text-gray-500">{l.text}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        {level === "custom" && (
          <div>
            <p className="mb-2 text-sm font-medium text-gray-700">What this admin can do</p>
            <div className="grid gap-3 md:grid-cols-2">
              {groups.map((g) => {
                const codes = g.permissions.map((p) => p.code);
                const all = codes.every((c) => perms.has(c));
                return (
                  <div key={g.key} className="rounded-lg border border-surface-border p-3">
                    <div className="mb-1.5 flex items-center justify-between">
                      <p className="text-xs font-bold uppercase tracking-wide text-gray-500">{g.label}</p>
                      <button type="button" className="text-[11px] font-semibold text-brand-600 hover:text-brand-700" onClick={() => toggleGroup(codes, !all)}>
                        {all ? "Clear" : "Select all"}
                      </button>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {g.permissions.map((p) => (
                        <label key={p.code} className="flex items-start gap-2 text-sm text-gray-700">
                          <input type="checkbox" checked={perms.has(p.code)} onChange={() => toggle(p.code)} className="mt-0.5 h-4 w-4 rounded border-surface-border text-brand-500 focus:ring-brand-500" />
                          {p.description}
                        </label>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {error && <p className="text-sm text-status-danger">{error}</p>}
      </form>
    </Modal>
  );
}
