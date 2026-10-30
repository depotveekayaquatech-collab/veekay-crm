import { EntryRoleSection } from "@/features/team/EntryRoleSection";
import { useAuth } from "@/features/auth/useAuth";
import { useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { PermissionGrid } from "@/features/team/PermissionGrid";
import { ScopePicker } from "@/features/team/ScopePicker";
import { useAllRegions } from "@/features/regions/useRegions";
import { useAllStores } from "@/features/stores/useAllStores";
import { usePartners } from "@/features/stores/useStores";
import { usePermissionGroups, useTeamMutations } from "@/features/team/useTeam";
import type { Employee } from "@/types/employee";

const EMPLOYEE_MODEL_SLUGS = ["zepto"];

interface Props {
  onClose: () => void;
  employee?: Employee | null;
}

export function EmployeeAccessModal({ onClose, employee }: Props) {
  const { hasRole } = useAuth();
  const editing = Boolean(employee);
  const { create, update, setScope, setPermissions } = useTeamMutations();
  const { data: regions = [] } = useAllRegions(employee?.regions.map((r) => r.id));
  const { data: partners = [] } = usePartners();
  const { data: groups = [] } = usePermissionGroups();

  const [code, setCode] = useState(employee?.employeeCode ?? "");
  const [name, setName] = useState(employee?.fullName ?? "");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState(employee?.email ?? "");
  const [platformId, setPlatformId] = useState(employee?.platformId ?? "");
  const [regionIds, setRegionIds] = useState<string[]>(employee?.regions.map((r) => r.id) ?? []);
  const [excludedStates, setExcludedStates] = useState<string[]>(employee?.excludedStates ?? []);
  const [excludedCities, setExcludedCities] = useState<string[]>(employee?.excludedCities ?? []);
  const [includedStates, setIncludedStates] = useState<string[]>(employee?.includedStates ?? []);
  const [includedCities, setIncludedCities] = useState<string[]>(employee?.includedCities ?? []);
  // "*" among the added states = every store of the platform (state-scoped platforms like Zepto have no other way to give someone all states)
  const [allStores, setAllStores] = useState<boolean>(employee?.includedStates?.includes("*") ?? false);
  const [perms, setPerms] = useState<Set<string>>(
    // New employees start with ticket access for their own region; everything else stays opt-in.
    new Set(employee?.directPermissions ?? ["tickets.view", "tickets.create"]),
  );
  const [error, setError] = useState<string | null>(null);

  const platformSlug = partners.find((p) => p.id === platformId)?.slug ?? "";
  const isEmployeeModel = EMPLOYEE_MODEL_SLUGS.includes(platformSlug);

  // The Region list follows the Platform: only regions that have stores of that platform (all of them when no
  // platform is picked, or the platform has no regions yet so nobody is locked out). The saved region always stays.
  const { data: stores = [] } = useAllStores();
  const regionsFor = (slug: string) => {
    if (!slug) return regions;
    const ids = new Set(stores.filter((s) => s.partnerSlug === slug && s.regionId).map((s) => s.regionId));
    const scoped = regions.filter((r) => ids.has(r.id) || employee?.regions.some((x) => x.id === r.id));
    return scoped.length ? scoped : regions;
  };
  const regionOptions = useMemo(() => regionsFor(platformSlug), [regions, stores, platformSlug]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const picked = isEmployeeModel ? [] : regionIds;
      const skipS = isEmployeeModel ? [] : excludedStates;
      const skipC = isEmployeeModel ? [] : excludedCities;
      const addS = isEmployeeModel ? (allStores ? ["*"] : []) : includedStates;
      const addC = isEmployeeModel ? [] : includedCities;
      if (employee) {
        await update.mutateAsync({ id: employee.id, input: { full_name: name, email: email || null } });
        await setScope.mutateAsync({ id: employee.id, platformId: platformId || null, regionIds: picked, excludedStates: skipS, excludedCities: skipC, includedStates: addS, includedCities: addC });
        await setPermissions.mutateAsync({ id: employee.id, codes: [...perms] });
      } else {
        const created = await create.mutateAsync({
          employee_code: code,
          full_name: name,
          password,
          email: email || null,
          platform_id: platformId || null,
          region_id: picked[0] ?? null,
          permission_codes: [...perms],
        });
        // Several regions or skipped places are saved right after the account exists.
        if (picked.length > 1 || skipS.length || skipC.length || addS.length || addC.length) {
          await setScope.mutateAsync({ id: created.id, platformId: platformId || null, regionIds: picked, excludedStates: skipS, excludedCities: skipC, includedStates: addS, includedCities: addC });
        }
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
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@gmail.com"
          hint="Needed for Forgot password: the 6-digit reset code is emailed here. Use an address this person can open." />
        {employee && (hasRole("admin") || hasRole("developer")) && <EntryRoleSection employee={employee} />}

        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Platform"
            value={platformId}
            onChange={(e) => {
              const id = e.target.value;
              setPlatformId(id);
              // A region that doesn't belong to the newly chosen platform is cleared.
              const slug = partners.find((p) => p.id === id)?.slug ?? "";
              const allowed = new Set(regionsFor(slug).map((r) => r.id));
              setRegionIds((ids) => ids.filter((r) => allowed.has(r)));
            }}
            placeholder="None"
            options={partners.map((p) => ({ value: p.id, label: p.name }))}
          />
        </div>
        {!isEmployeeModel && (
          <div className="flex flex-col gap-1.5">
            <p className="text-[13px] font-semibold text-gray-700">Regions</p>
            <ScopePicker
              platformSlug={platformSlug}
              regionOptions={regionOptions.map((r) => ({ id: r.id, name: r.name }))}
              regionIds={regionIds}
              onRegionIds={setRegionIds}
              excludedStates={excludedStates}
              onExcludedStates={setExcludedStates}
              excludedCities={excludedCities}
              onExcludedCities={setExcludedCities}
              includedStates={includedStates}
              onIncludedStates={setIncludedStates}
              includedCities={includedCities}
              onIncludedCities={setIncludedCities}
            />
          </div>
        )}
        {isEmployeeModel && (
          <p className="rounded-md bg-surface-subtle px-3 py-2 text-xs text-gray-500">
            {platformSlug} employees are scoped by <strong>state</strong>: assign states on the
            State assignment panel after creating this employee.
          </p>
        )}
        {isEmployeeModel && (
          <label className="flex items-start gap-2.5 rounded-md border border-surface-border px-3 py-2.5 text-sm text-gray-700">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand-500" checked={allStores} onChange={(e) => setAllStores(e.target.checked)} />
            <span>
              <strong className="font-semibold">Can mark every {platformSlug} store</strong>
              <span className="block text-xs text-gray-500">All states, including new ones, in addition to any states assigned above. Marking rules are unchanged.</span>
            </span>
          </label>
        )}

        <div>
          <p className="mb-2 text-sm font-medium text-gray-700">What this employee can do</p>
          <PermissionGrid groups={groups} value={perms} onChange={setPerms} />
        </div>

        {error && <p className="text-sm text-status-danger">{error}</p>}
      </form>
    </Modal>
  );
}
