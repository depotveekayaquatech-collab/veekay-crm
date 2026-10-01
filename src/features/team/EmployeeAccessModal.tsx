import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { useAllRegions } from "@/features/regions/useRegions";
import { usePartners } from "@/features/stores/useStores";
import { usePermissionGroups, useTeamMutations } from "@/features/team/useTeam";
import type { Employee } from "@/types/employee";

const EMPLOYEE_MODEL_SLUGS = ["zepto"];

interface Props {
  onClose: () => void;
  employee?: Employee | null;
}

export function EmployeeAccessModal({ onClose, employee }: Props) {
  const editing = Boolean(employee);
  const { create, update, setScope, setPermissions } = useTeamMutations();
  const { data: regions = [] } = useAllRegions();
  const { data: partners = [] } = usePartners();
  const { data: groups = [] } = usePermissionGroups();

  const [code, setCode] = useState(employee?.employeeCode ?? "");
  const [name, setName] = useState(employee?.fullName ?? "");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState(employee?.email ?? "");
  const [platformId, setPlatformId] = useState(employee?.platformId ?? "");
  const [regionId, setRegionId] = useState(employee?.regionId ?? "");
  const [perms, setPerms] = useState<Set<string>>(
    // New employees start with ticket access for their own region; everything else stays opt-in.
    new Set(employee?.directPermissions ?? ["tickets.view", "tickets.create"]),
  );
  const [error, setError] = useState<string | null>(null);

  const platformSlug = partners.find((p) => p.id === platformId)?.slug ?? "";
  const isEmployeeModel = EMPLOYEE_MODEL_SLUGS.includes(platformSlug);

  function toggle(codeStr: string) {
    setPerms((prev) => {
      const next = new Set(prev);
      if (next.has(codeStr)) next.delete(codeStr);
      else next.add(codeStr);
      return next;
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const region = isEmployeeModel ? null : regionId || null;
      if (employee) {
        await update.mutateAsync({ id: employee.id, input: { full_name: name, email: email || null } });
        await setScope.mutateAsync({ id: employee.id, platformId: platformId || null, regionId: region });
        await setPermissions.mutateAsync({ id: employee.id, codes: [...perms] });
      } else {
        await create.mutateAsync({
          employee_code: code,
          full_name: name,
          password,
          email: email || null,
          platform_id: platformId || null,
          region_id: region,
          permission_codes: [...perms],
        });
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
      title={editing ? `Edit ${employee?.employeeCode}` : "New employee"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" form="emp-form" isLoading={busy}>{editing ? "Save" : "Create"}</Button>
        </>
      }
    >
      <form id="emp-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Employee ID"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            required
            disabled={editing}
            autoFocus={!editing}
          />
          <Input label="Full name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        {!editing && (
          <Input
            label="Initial password"
            type="text"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            hint="At least 8 characters. Share it with the employee."
            required
            minLength={8}
          />
        )}
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Optional" />

        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Platform"
            value={platformId}
            onChange={(e) => setPlatformId(e.target.value)}
            placeholder="None"
            options={partners.map((p) => ({ value: p.id, label: p.name }))}
          />
          {!isEmployeeModel && (
            <Select
              label="Region"
              value={regionId}
              onChange={(e) => setRegionId(e.target.value)}
              placeholder="None"
              options={regions.map((r) => ({ value: r.id, label: r.name }))}
            />
          )}
        </div>
        {isEmployeeModel && (
          <p className="rounded-md bg-surface-subtle px-3 py-2 text-xs text-gray-500">
            {platformSlug} employees are scoped by <strong>state</strong> — assign states on the
            State assignment panel after creating this employee.
          </p>
        )}

        <div>
          <p className="mb-2 text-sm font-medium text-gray-700">What this employee can do</p>
          <div className="space-y-3">
            {groups.map((g) => (
              <div key={g.key}>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{g.label}</p>
                <div className="mt-1 grid gap-1.5 sm:grid-cols-2">
                  {g.permissions.map((p) => (
                    <label key={p.code} className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={perms.has(p.code)}
                        onChange={() => toggle(p.code)}
                        className="h-4 w-4 rounded border-surface-border text-brand-500 focus:ring-brand-500"
                      />
                      {p.description}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="text-sm text-status-danger">{error}</p>}
      </form>
    </Modal>
  );
}
